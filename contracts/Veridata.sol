// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Veridata: device registry, dataset licensing and request escrow in one contract
/// @notice Self-contained (no imports) so it compiles and deploys directly in Remix.
///         Payments are in native ETH (Sepolia). Constructor:
///           Veridata(treasury, uploadFeeWei, platformFeeBps)   (treasury 0x0 = deployer)
///
///  Devices   : on-chain reference to a capture device's P-256 public key (no personal data).
///  Datasets  : contentRoot = sha256 Merkle root of signed capture manifests; storageRef points
///              to encrypted storage. Licenses are a non-transferable (dataset, buyer) flag that
///              grants training access inside the platform's controlled environment.
///  Escrow    : the buyer funds pricePerSample * quantity. The platform checks submitted samples
///              off-chain; the BUYER then releases payouts for verified samples from their own
///              wallet (releasePayouts). Each sample hash can be paid only once (global). The buyer
///              reclaims the unreleased balance after the deadline or once filled.
///  No platform-held private key: every transaction is signed by a user's wallet.
/// @dev Not audited.
contract Veridata {
    // ---------------------------------------------------------------- config
    address public admin;
    address public treasury;
    uint256 public uploadFee;
    uint16 public platformFeeBps;

    uint256 private _lock = 1;
    modifier nonReentrant() {
        require(_lock == 1, "reentrancy");
        _lock = 2;
        _;
        _lock = 1;
    }
    modifier onlyAdmin() {
        require(msg.sender == admin, "not admin");
        _;
    }

    constructor(address _treasury, uint256 _uploadFee, uint16 _feeBps) {
        require(_feeBps <= 2000, "fee too high");
        admin = msg.sender;
        treasury = _treasury == address(0) ? msg.sender : _treasury;
        uploadFee = _uploadFee;
        platformFeeBps = _feeBps;
    }

    function setConfig(address _treasury, uint256 _uploadFee, uint16 _feeBps) external onlyAdmin {
        require(_feeBps <= 2000, "fee too high");
        require(_treasury != address(0), "treasury");
        treasury = _treasury;
        uploadFee = _uploadFee;
        platformFeeBps = _feeBps;
    }

    function _send(address to, uint256 amount) internal {
        if (amount == 0) return;
        (bool ok, ) = payable(to).call{value: amount}("");
        require(ok, "transfer failed");
    }

    function _fee(uint256 amount) internal view returns (uint256) {
        return (amount * platformFeeBps) / 10_000;
    }

    // ---------------------------------------------------------------- devices
    struct Device {
        address owner;
        bytes pubKey; // 0x04 || X || Y (P-256)
        uint64 registeredAt;
        bool active;
    }
    mapping(bytes32 => Device) private _devices;

    event DeviceRegistered(bytes32 indexed deviceId, address indexed owner, bytes pubKey, string meta);
    event DeviceRevoked(bytes32 indexed deviceId, address indexed owner);

    function registerDevice(bytes32 deviceId, bytes calldata pubKey, string calldata meta) external {
        require(_devices[deviceId].owner == address(0), "already registered");
        require(pubKey.length == 65 && pubKey[0] == 0x04, "bad key");
        _devices[deviceId] = Device(msg.sender, pubKey, uint64(block.timestamp), true);
        emit DeviceRegistered(deviceId, msg.sender, pubKey, meta);
    }

    function revokeDevice(bytes32 deviceId) external {
        require(_devices[deviceId].owner == msg.sender, "not owner");
        _devices[deviceId].active = false;
        emit DeviceRevoked(deviceId, msg.sender);
    }

    function getDevice(bytes32 deviceId) external view returns (address owner, bytes memory pubKey, uint64 registeredAt, bool active) {
        Device storage d = _devices[deviceId];
        return (d.owner, d.pubKey, d.registeredAt, d.active);
    }

    // ---------------------------------------------------------------- datasets & licenses
    struct Dataset {
        address owner;
        bytes32 contentRoot;
        uint256 price;
        uint64 publishedAt;
        bool listed;
        string storageRef;
    }
    uint256 public nextDatasetId = 1;
    mapping(uint256 => Dataset) public datasets;
    mapping(uint256 => mapping(address => bool)) private _licensed;

    event DatasetPublished(uint256 indexed datasetId, address indexed owner, bytes32 contentRoot, uint256 price, string storageRef);
    event DatasetUpdated(uint256 indexed datasetId, uint256 price, bool listed);
    event LicensePurchased(uint256 indexed datasetId, address indexed buyer, address indexed seller, uint256 price, uint256 platformFee);

    function publishDataset(bytes32 contentRoot, uint256 price, string calldata storageRef) external payable nonReentrant returns (uint256 id) {
        require(msg.value == uploadFee, "upload fee");
        id = nextDatasetId++;
        datasets[id] = Dataset(msg.sender, contentRoot, price, uint64(block.timestamp), true, storageRef);
        _send(treasury, msg.value);
        emit DatasetPublished(id, msg.sender, contentRoot, price, storageRef);
    }

    function updateDataset(uint256 id, uint256 price, bool listed) external {
        require(datasets[id].owner == msg.sender, "not owner");
        datasets[id].price = price;
        datasets[id].listed = listed;
        emit DatasetUpdated(id, price, listed);
    }

    function purchaseLicense(uint256 id) external payable nonReentrant {
        require(msg.value == datasets[id].price, "wrong amount");
        _grant(id, msg.sender);
    }

    function _grant(uint256 id, address buyer) internal {
        Dataset storage d = datasets[id];
        require(d.owner != address(0) && d.listed, "not listed");
        require(!_licensed[id][buyer], "already licensed");
        _licensed[id][buyer] = true;
        uint256 fee = _fee(d.price);
        _send(treasury, fee);
        _send(d.owner, d.price - fee);
        emit LicensePurchased(id, buyer, d.owner, d.price, fee);
    }

    function hasLicense(uint256 id, address user) external view returns (bool) {
        return _licensed[id][user] || (datasets[id].owner == user && user != address(0));
    }

    // ---------------------------------------------------------------- request escrow
    struct Request {
        address buyer;
        bytes32 specHash;
        uint256 pricePerSample;
        uint32 quantity;
        uint32 accepted;
        uint256 deposited;
        uint256 released;
        uint64 deadline;
        bool closed;
    }
    uint256 public nextRequestId = 1;
    mapping(uint256 => Request) public requests;
    mapping(bytes32 => bool) public claimedSample;

    event RequestFunded(uint256 indexed requestId, address indexed buyer, bytes32 specHash, uint256 pricePerSample, uint32 quantity, uint64 deadline, uint256 deposited);
    event SampleAccepted(uint256 indexed requestId, bytes32 indexed sampleHash, address indexed contributor, uint256 payout, uint256 platformFee, uint32 acceptedCount);
    event RequestClosed(uint256 indexed requestId, uint256 refunded);

    function createRequest(bytes32 specHash, uint256 pricePerSample, uint32 quantity, uint64 deadline) external payable nonReentrant returns (uint256 id) {
        require(pricePerSample > 0 && quantity > 0 && deadline > block.timestamp, "bad params");
        require(msg.value == pricePerSample * quantity, "deposit");
        id = nextRequestId++;
        requests[id] = Request(msg.sender, specHash, pricePerSample, quantity, 0, msg.value, 0, deadline, false);
        emit RequestFunded(id, msg.sender, specHash, pricePerSample, quantity, deadline, msg.value);
    }

    /// @notice Buyer pays contributors for samples the platform has verified. Batch of up to 50.
    function releasePayouts(uint256 id, bytes32[] calldata sampleHashes, address[] calldata contributors) external nonReentrant {
        Request storage r = requests[id];
        require(msg.sender == r.buyer, "not buyer");
        require(!r.closed, "closed");
        uint256 n = sampleHashes.length;
        require(n > 0 && n <= 50 && n == contributors.length, "bad batch");
        require(r.accepted + n <= r.quantity, "exceeds quantity");
        uint256 fee = _fee(r.pricePerSample);
        uint256 payout = r.pricePerSample - fee;
        for (uint256 i = 0; i < n; i++) {
            require(contributors[i] != address(0), "contributor");
            require(!claimedSample[sampleHashes[i]], "already claimed");
            claimedSample[sampleHashes[i]] = true;
            r.accepted += 1;
            r.released += r.pricePerSample;
            _send(contributors[i], payout);
            emit SampleAccepted(id, sampleHashes[i], contributors[i], payout, fee, r.accepted);
        }
        _send(treasury, fee * n);
    }

    function closeAndRefund(uint256 id) external nonReentrant {
        Request storage r = requests[id];
        require(msg.sender == r.buyer, "not buyer");
        require(!r.closed, "closed");
        require(block.timestamp > r.deadline || r.accepted >= r.quantity, "not refundable yet");
        r.closed = true;
        uint256 refund = r.deposited - r.released;
        _send(r.buyer, refund);
        emit RequestClosed(id, refund);
    }

    function remaining(uint256 id) external view returns (uint256) {
        Request storage r = requests[id];
        return r.closed ? 0 : r.deposited - r.released;
    }
}
