// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// Minimal EIP-3009 surface of Whitechain Sepolia USDT (0xcedfB56113143d55b2358b8CFbB0dEB5Ad2f55a7).
interface IUSDT3009 {
    function receiveWithAuthorization(
        address from, address to, uint256 value,
        uint256 validAfter, uint256 validBefore, bytes32 nonce,
        uint8 v, bytes32 r, bytes32 s
    ) external;
    function transfer(address to, uint256 value) external returns (bool);
}

/// @title VeridataPay - gasless USDT checkout for Veridata dataset licenses (Whitechain Sepolia, chain 1874)
/// @notice The buyer (a person or an AI agent) holds only USDT and signs one EIP-3009
///         ReceiveWithAuthorization. Anyone may submit it (Veridata runs a relayer that pays the WBT gas).
///         The authorization nonce commits to (chain, this contract, datasetId, seller, salt), so the
///         submitter cannot redirect the money to another seller or dataset, and `receiveWithAuthorization`
///         requires `to == msg.sender`, so nobody can front-run the signature into a plain transfer.
///         The contract never holds funds after a call: the split is paid out in the same transaction.
contract VeridataPay {
    IUSDT3009 public immutable usdt;
    address public immutable treasury;
    uint16 public immutable feeBps; // platform fee, e.g. 500 = 5%

    /// datasetId => buyer => licensed
    mapping(uint256 => mapping(address => bool)) public hasLicense;

    event LicensePurchased(
        uint256 indexed datasetId, address indexed buyer, address indexed seller,
        uint256 price, uint256 platformFee, bytes32 nonce
    );

    error AlreadyLicensed();
    error BadParams();
    error TransferFailed();

    constructor(address _usdt, address _treasury, uint16 _feeBps) {
        if (_usdt == address(0) || _treasury == address(0) || _feeBps > 2000) revert BadParams();
        usdt = IUSDT3009(_usdt);
        treasury = _treasury;
        feeBps = _feeBps;
    }

    /// @notice The EIP-3009 nonce the buyer must sign for this purchase.
    function purchaseNonce(uint256 datasetId, address seller, bytes32 salt) public view returns (bytes32) {
        return keccak256(abi.encode(block.chainid, address(this), datasetId, seller, salt));
    }

    /// @notice Settle a signed USDT authorization into a dataset license.
    function purchase(
        uint256 datasetId, address seller, address buyer, uint256 price,
        uint256 validAfter, uint256 validBefore, bytes32 salt,
        uint8 v, bytes32 r, bytes32 s
    ) external {
        if (seller == address(0) || price == 0 || seller == buyer) revert BadParams();
        if (hasLicense[datasetId][buyer]) revert AlreadyLicensed();
        bytes32 nonce = purchaseNonce(datasetId, seller, salt);

        // Pulls `price` USDT from the buyer into this contract; reverts on a bad/used/expired signature.
        usdt.receiveWithAuthorization(buyer, address(this), price, validAfter, validBefore, nonce, v, r, s);

        hasLicense[datasetId][buyer] = true;
        uint256 fee = (price * feeBps) / 10_000;
        _pay(seller, price - fee);
        if (fee > 0) _pay(treasury, fee);

        emit LicensePurchased(datasetId, buyer, seller, price, fee, nonce);
    }

    /// USDT-style tokens may return nothing from transfer(); accept empty or `true`.
    function _pay(address to, uint256 amount) private {
        (bool ok, bytes memory ret) = address(usdt).call(abi.encodeCall(IUSDT3009.transfer, (to, amount)));
        if (!ok || (ret.length != 0 && !abi.decode(ret, (bool)))) revert TransferFailed();
    }
}
