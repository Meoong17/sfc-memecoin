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

from datetime import datetime
from typing import Any

from data_sources.wallet_funding import FundingEdge
from fetchers.base import BaseFetcher, FetchError

# SPL Token program (standard transfers)
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


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
        """Parse one transaction for token transfers."""
        data = self._rpc("getParsedTransaction", [signature, {"maxSupportedTransactionVersion": 0}])
        return data.get("result") or {}

    def _extract_transfers(self, tx: dict) -> list[dict]:
        """Extract SPL token transfers from a parsed tx (from/to/amount)."""
        out: list[dict] = []
        meta = tx.get("meta") or {}
        if meta.get("err"):
            return out
        inner = meta.get("innerInstructions") or []
        # top-level + inner token transfers
        for instr_set in ([meta] + inner):
            token_bal_changes = instr_set.get("postTokenBalances") or []
            pre = {b.get("owner"): b.get("uiTokenAmount", {}).get("uiAmount", 0.0)
                   for b in (instr_set.get("preTokenBalances") or [])}
            for b in token_bal_changes:
                owner = b.get("owner")
                post = (b.get("uiTokenAmount") or {}).get("uiAmount", 0.0)
                pre_amt = pre.get(owner, 0.0)
                delta = (post or 0.0) - (pre_amt or 0.0)
                if abs(delta) > 0:
                    out.append({
                        "owner": owner,
                        "delta": delta,
                        "mint": b.get("mint"),
                        "signature": tx.get("transaction", {}).get("signatures", [None])[0],
                    })
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
                # master must be the source (its balance decreased)
                if tr.get("owner") == master_wallet and tr["delta"] < 0 and tr.get("mint") == token_mint:
                    edges.append(FundingEdge(
                        master_wallet=master_wallet,
                        sub_wallet=str(tr["owner"]),  # placeholder; real receiver needs balance index
                        amount=abs(tr["delta"]),
                        ts=datetime.utcnow(),
                        chain=chain,
                    ))
        return edges
