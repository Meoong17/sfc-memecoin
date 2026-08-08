"""Helius RPC fetcher — funding trace (EV-021 producer input).

Pulls on-chain history to trace master->sub-wallet funding relationships:
  1. getSignaturesForAddress(wallet)  -> list wallet's outgoing transfers
  2. getTokenAccountsByOwner           -> which tokens a wallet holds
  3. getParsedTransaction              -> decode transfers (amount, from, to)

Maps into data_sources.wallet_funding.FundingEdge (EV-021) and provides raw
wallet activity the funding graph groups into clusters.

Requires HELIUS_API_KEY in .env. Uses the enhanced RPC endpoint:
  POST https://mainnet.helius-rpc.com/?api-key=KEY
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from data_sources.wallet_funding import FundingEdge
from fetchers.base import BaseFetcher, FetchError

# SPL Token program (standard transfers)
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


def _amount_of(info: dict, ptype: str) -> float:
    """Extract transfer amount from parsed instruction info.

    transferChecked carries tokenAmount; plain transfer carries amount.
    Normalizes raw token units to a comparable float (raw units, not decimals).
    """
    if ptype in ("transferChecked", "transferCheck"):
        ta = info.get("tokenAmount") or {}
        amt = ta.get("amount")
        if amt is not None:
            try:
                return float(amt)
            except (TypeError, ValueError):
                return 0.0
    amt = info.get("amount")
    if amt is None:
        return 0.0
    try:
        return float(amt)
    except (TypeError, ValueError):
        return 0.0


class HeliusRpcFetcher(BaseFetcher):
    """Fetches Solana on-chain data via Helius enhanced RPC."""

    def __init__(self, api_key: str | None = None, *, cache_dir: str | None = None,
                 cache_ttl: int = 300) -> None:
        import os
        self.api_key = api_key or os.getenv("HELIUS_API_KEY")
        if not self.api_key:
            raise ValueError("HELIUS_API_KEY missing (set in .env or pass api_key=)")
        self.url = f"https://mainnet.helius-rpc.com/?api-key={self.api_key}"
        super().__init__(source="rpc", cache_dir=cache_dir, cache_ttl=cache_ttl)

    def _rpc(self, method: str, params: list, cache_key: str | None = None) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        return self._post_json(self.url, payload, cache_key=cache_key)

    def get_signatures(self, address: str, *, limit: int = 100,
                       before: str | None = None) -> list[dict]:
        """List transaction signatures for a wallet (newest first)."""
        params: list = [address, {"limit": min(limit, 1000)}]
        if before:
            params[1]["before"] = before
        data = self._rpc("getSignaturesForAddress", params)
        return data.get("result") or []

    def get_parsed_transaction(self, signature: str) -> dict:
        """Parse one transaction for token transfers.

        Uses the standard `getTransaction` method (getParsedTransaction is NOT
        exposed on the Helius enhanced RPC endpoint — verified live: method not
        found). Version 0 handles Solana's current tx version.
        """
        data = self._rpc("getTransaction",
                         [signature, {"maxSupportedTransactionVersion": 0,
                                      "encoding": "jsonParsed"}])
        return data.get("result") or {}

    def _extract_transfers(self, tx: dict) -> list[dict]:
        """Extract SPL token transfers from a parsed tx (from/to/amount).

        Uses the PARSED INSTRUCTIONS (source/destination fields) — the correct
        source of truth for receiver identity, not just balance-delta owners
        (which often equal the wallet itself). Verified live on Helius.
        """
        out: list[dict] = []
        meta = tx.get("meta") or {}
        if meta.get("err"):
            return out
        msg = tx.get("transaction", {}).get("message", {})
        sig = (tx.get("transaction", {}).get("signatures") or [None])[0]

        # gather all instructions incl. inner
        instructions: list = list(msg.get("instructions") or [])
        for inner in (meta.get("innerInstructions") or []):
            instructions.extend(inner.get("instructions") or [])

        for inst in instructions:
            if not isinstance(inst, dict):
                continue
            parsed = inst.get("parsed") or {}
            ptype = parsed.get("type") or ""
            info = parsed.get("info") or {}
            program = inst.get("program", "")

            # SPL token transfer or system transfer: has source/destination
            if ptype in ("transfer", "transferChecked", "transferCheck") or \
               (program == "spl-token" and ptype in ("transfer", "transferChecked")):
                src = info.get("source")
                dst = info.get("destination")
                amount = _amount_of(info, ptype)
                mint = info.get("mint")
                if src and dst and amount and amount > 0:
                    out.append({"source": src, "destination": dst,
                                "amount": amount, "mint": mint, "signature": sig})
        return out

    def fetch_funding_edges(self, master_wallet: str, *, token_mint: str,
                            chain: str = "solana", max_tx: int = 200) -> list[FundingEdge]:
        """Trace transfers FROM a master wallet and map to FundingEdge (EV-021).

        Conservative approach: signatures of the master, parse each, extract
        token transfers, keep those where the master is the SOURCE (negative
        delta) -> sub-wallet receiving. Batched/cached to respect rate limits.
        """
        edges: list[FundingEdge] = []
        try:
            sigs = self.get_signatures(master_wallet, limit=max_tx)
        except FetchError as e:
            raise FetchError(f"getSignaturesForAddress {master_wallet}: {e}") from e

        for s in sigs[:max_tx]:
            sig = s.get("signature")
            if not sig:
                continue
            try:
                tx = self.get_parsed_transaction(sig)
            except FetchError:
                continue
            for tr in self._extract_transfers(tx):
                # master must be the SOURCE (outgoing transfer); receiver is
                # destination (correct identity from parsed instructions).
                if tr.get("source") == master_wallet and tr.get("mint") == token_mint:
                    edges.append(FundingEdge(
                        master_wallet=master_wallet,
                        sub_wallet=tr["destination"],
                        amount=tr["amount"],
                        ts=datetime.now(timezone.utc),
                        chain=chain,
                    ))
        return edges
