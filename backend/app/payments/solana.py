"""Minimal Solana helpers: JSON-RPC, deposit-key derivation, SOL and SPL-token transfers. Untested on mainnet."""
from __future__ import annotations

import base64
import hashlib
import hmac
import struct
from typing import Any

import httpx
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction

TOKEN_PROGRAM = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ATA_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
SYSTEM_PROGRAM = Pubkey.from_string("11111111111111111111111111111111")

_decimals_cache: dict[str, int] = {}


class RpcError(Exception):
    pass


class Rpc:
    def __init__(self, url: str, client: httpx.Client | None = None) -> None:
        if not url:
            raise RpcError("SOLANA_RPC_URL is not set")
        self._url = url
        self._c = client or httpx.Client(timeout=15)

    def call(self, method: str, params: list[Any]) -> Any:
        try:
            body = self._c.post(self._url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RpcError(f"{method} failed ({type(exc).__name__})") from None   # never include the URL (API key)
        if isinstance(body, dict) and body.get("error"):
            raise RpcError(f"{method}: {body['error'].get('message', 'error')}")
        return body.get("result")

    def close(self) -> None:
        self._c.close()


def derive_deposit_keypair(master_seed_hex: str, user_id: Any) -> Keypair:
    if len(master_seed_hex) != 64:
        raise ValueError("DEPOSIT_MASTER_SEED must be 64 hex characters")
    seed = hmac.new(bytes.fromhex(master_seed_hex), f"wd-deposit-v1:{user_id}".encode(), hashlib.sha256).digest()
    return Keypair.from_seed(seed)


def token_account_for(owner: Pubkey, mint: Pubkey) -> Pubkey:
    return Pubkey.find_program_address([bytes(owner), bytes(TOKEN_PROGRAM), bytes(mint)], ATA_PROGRAM)[0]


def mint_decimals(rpc: Rpc, mint: str) -> int:
    """Reads the decimals from the chain and refuses anything that is not a classic SPL token."""
    if mint in _decimals_cache:
        return _decimals_cache[mint]
    value = (rpc.call("getAccountInfo", [mint, {"encoding": "jsonParsed"}]) or {}).get("value")
    if not value or value.get("owner") != str(TOKEN_PROGRAM):
        raise RpcError("the WIENER mint is not a classic SPL token (Token-2022 is not supported)")
    _decimals_cache[mint] = int(value["data"]["parsed"]["info"]["decimals"])
    return _decimals_cache[mint]


def transfer_checked_ix(src: Pubkey, mint: Pubkey, dst: Pubkey, authority: Pubkey, amount: int, decimals: int) -> Instruction:
    data = bytes([12]) + struct.pack("<QB", amount, decimals)
    return Instruction(TOKEN_PROGRAM, data, [
        AccountMeta(src, False, True), AccountMeta(mint, False, False),
        AccountMeta(dst, False, True), AccountMeta(authority, True, False),
    ])


def create_ata_idempotent_ix(payer: Pubkey, ata: Pubkey, owner: Pubkey, mint: Pubkey) -> Instruction:
    return Instruction(ATA_PROGRAM, bytes([1]), [
        AccountMeta(payer, True, True), AccountMeta(ata, False, True), AccountMeta(owner, False, False),
        AccountMeta(mint, False, False), AccountMeta(SYSTEM_PROGRAM, False, False), AccountMeta(TOKEN_PROGRAM, False, False),
    ])


def system_transfer_ix(src: Pubkey, dst: Pubkey, lamports: int) -> Instruction:
    return Instruction(SYSTEM_PROGRAM, struct.pack("<IQ", 2, lamports), [
        AccountMeta(src, True, True), AccountMeta(dst, False, True),
    ])


def sign_tx(rpc: Rpc, instructions: list[Instruction], payer: Keypair, extra: list[Keypair] | None = None) -> tuple[str, str]:
    """Returns (signature, base64 transaction). The signature is known BEFORE sending."""
    blockhash = rpc.call("getLatestBlockhash", [{"commitment": "confirmed"}])["value"]["blockhash"]
    tx = Transaction.new_signed_with_payer(instructions, payer.pubkey(), [payer, *(extra or [])], Hash.from_string(blockhash))
    return str(tx.signatures[0]), base64.b64encode(bytes(tx)).decode()


def send_tx(rpc: Rpc, raw_b64: str) -> str:
    return rpc.call("sendTransaction", [raw_b64, {"encoding": "base64", "preflightCommitment": "confirmed"}])


def get_balance(rpc: Rpc, address: str) -> int:
    return int(rpc.call("getBalance", [address, {"commitment": "finalized"}])["value"])


def token_balance(rpc: Rpc, token_account: str) -> int:
    try:
        res = rpc.call("getTokenAccountBalance", [token_account, {"commitment": "finalized"}])
        return int(res["value"]["amount"])
    except (RpcError, KeyError, TypeError, ValueError):
        return 0      # account does not exist yet