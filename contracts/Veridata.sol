// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Veridata — device registry, dataset licensing and request escrow in one contract
/// @notice Self-contained (no imports) so it compiles and deploys directly in Remix.
///         Payments are in native ETH (Sepolia). Constructor:
///           Veridata(verifier, treasury, uploadFeeWei, platformFeeBps)
///
///  Devices   : on-chain reference to a capture device's P-256 public key (no personal data).
///  Datasets  : contentRoot = sha256 Merkle root of signed capture manifests; storageRef points
///              to encrypted storage. Licenses are a non-transferable (dataset, buyer) flag that
///              grants training access inside the platform's controlled environment.
///  x402-style: buyers prepay `credit`, then sign EIP-712 PaymentIntents per purchase; the
///              platform facilitator relays them and pays gas.
///  Escrow    : buyer funds pricePerSample * quantity; the verifier releases one payout per
///              accepted sample; each sample hash can be paid only once (global); the buyer
///              reclaims the unreleased balance after the deadline or once filled.
/// @dev Verifier is a trusted platform role in this MVP. Not audited.
contract Veridata {
    // ---------------------------------------------------------------- config
    address public admin;
    address public verifier;
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

    constructor(address _verifier, address _treasury, uint256 _uploadFee, uint16 _feeBps) {
        require(_feeBps <= 2000, "fee too high");
        admin = msg.sender;
        verifier = _verifier == address(0) ? msg.sender : _verifier;
        treasury = _treasury == address(0) ? msg.sender : _treasury;
        uploadFee = _uploadFee;
        platformFeeBps = _feeBps;
    }

    function setConfig(address _verifier, address _treasury, uint256 _uploadFee, uint16 _feeBps) external onlyAdmin {
        require(_feeBps <= 2000, "fee too high");
        verifier = _verifier;
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
    event LicensePurchased(uint256 indexed datasetId, address indexed buyer, address indexed seller, uint256 price, uint256 platformFee, bool viaFacilitator);

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
        _grant(id, msg.sender, false);
    }

    function _grant(uint256 id, address buyer, bool viaFacilitator) internal {
        Dataset storage d = datasets[id];
        require(d.owner != address(0) && d.listed, "not listed");
        require(!_licensed[id][buyer], "already licensed");
        _licensed[id][buyer] = true;
        uint256 fee = _fee(d.price);
        _send(treasury, fee);
        _send(d.owner, d.price - fee);
        emit LicensePurchased(id, buyer, d.owner, d.price, fee, viaFacilitator);
    }

    function hasLicense(uint256 id, address user) external view returns (bool) {
        return _licensed[id][user] || (datasets[id].owner == user && user != address(0));
    }

    // ---------------------------------------------------------------- x402-style prepaid credit
    mapping(address => uint256) public credit;
    mapping(address => uint256) public nonces;

    event CreditDeposited(address indexed buyer, uint256 amount);
    event CreditWithdrawn(address indexed buyer, uint256 amount);

    bytes32 public constant PAYMENT_INTENT_TYPEHASH =
        keccak256("PaymentIntent(uint256 datasetId,address buyer,uint256 amount,uint256 nonce,uint256 deadline)");

    function depositCredit() external payable {
        credit[msg.sender] += msg.value;
        emit CreditDeposited(msg.sender, msg.value);
    }

    function withdrawCredit(uint256 amount) external nonReentrant {
        require(credit[msg.sender] >= amount, "insufficient");
        credit[msg.sender] -= amount;
        _send(msg.sender, amount);
        emit CreditWithdrawn(msg.sender, amount);
    }

    function domainSeparator() public view returns (bytes32) {
        return keccak256(abi.encode(
            keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
            keccak256(bytes("Veridata")), keccak256(bytes("1")), block.chainid, address(this)));
    }

    function purchaseLicenseWithSig(uint256 id, address buyer, uint256 amount, uint256 deadline, bytes calldata sig) external nonReentrant {
        require(block.timestamp <= deadline, "expired");
        require(amount == datasets[id].price, "wrong amount");
        bytes32 structHash = keccak256(abi.encode(PAYMENT_INTENT_TYPEHASH, id, buyer, amount, nonces[buyer], deadline));
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator(), structHash));
        require(_recover(digest, sig) == buyer, "bad signature");
        require(credit[buyer] >= amount, "insufficient credit");
        nonces[buyer]++;
        credit[buyer] -= amount;
        _grant(id, buyer, true);
    }

    function _recover(bytes32 digest, bytes calldata sig) internal pure returns (address) {
        require(sig.length == 65, "sig length");
        bytes32 r = bytes32(sig[0:32]);
        bytes32 s = bytes32(sig[32:64]);
        uint8 v = uint8(sig[64]);
        if (v < 27) v += 27;
        require(uint256(s) <= 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0, "bad s");
        address signer = ecrecover(digest, v, r, s);
        require(signer != address(0), "bad signature");
        return signer;
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

    function acceptSample(uint256 id, bytes32 sampleHash, address contributor) external nonReentrant {
        require(msg.sender == verifier, "not verifier");
        Request storage r = requests[id];
        require(r.buyer != address(0) && !r.closed, "closed");
        require(block.timestamp <= r.deadline, "expired");
        require(r.accepted < r.quantity, "full");
        require(!claimedSample[sampleHash], "already claimed");
        claimedSample[sampleHash] = true;
        r.accepted += 1;
        r.released += r.pricePerSample;
        uint256 fee = _fee(r.pricePerSample);
        _send(treasury, fee);
        _send(contributor, r.pricePerSample - fee);
        emit SampleAccepted(id, sampleHash, contributor, r.pricePerSample - fee, fee, r.accepted);
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
