        # ── "in" ─────────────────────────────────────────────────────────────
        # Covers both external deposits AND same-asset credits (origin==dest,
        # e.g. Brave Rewards BAT). In both cases the treatment is a BUY lot.
        if tx_type == "in":
            # Prefer dest_asset/dest_amount; fall back to origin for same-asset rows
            crypto_asset = dest_asset if (dest_asset and not _is_fiat(dest_asset)) else (
                origin_asset if (origin_asset and not _is_fiat(origin_asset)) else None
            )
            crypto_amount = dest_amount if dest_amount > 0 else origin_amount

            if not crypto_asset or crypto_amount <= 0:
                continue

            if skip_uphold_in:
                special_events.append(SpecialEvent(
                    date=date, asset=crypto_asset, event_type="skipped_deposit",
                    amount=crypto_amount, price=0.0, fee=0.0,
                    notes="deposit skipped (--skip-uphold-in): already counted in source exchange CSV",
                ))
            else:
                price = 0.0
                if price_loader and price_loader.has_asset(crypto_asset):
                    loaded_price = price_loader.get_price(crypto_asset, date)
                    if loaded_price is not None:
                        price = loaded_price
                trades.append(Trade(date=date, asset=crypto_asset, type="buy",
                                    amount=crypto_amount, price=price, fee=0.0))

        # ── "staking-reward" / "reward" ───────────────────────────────────────
        elif tx_type in {"staking-reward", "reward"}:
            crypto_asset = dest_asset if (dest_asset and not _is_fiat(dest_asset)) else (
                origin_asset if (origin_asset and not _is_fiat(origin_asset)) else None
            )
            crypto_amount = dest_amount if dest_amount > 0 else origin_amount

            if not crypto_asset or crypto_amount <= 0:
                continue

            price = 0.0
            if price_loader and price_loader.has_asset(crypto_asset):
                loaded_price = price_loader.get_price(crypto_asset, date)
                if loaded_price is not None:
                    price = loaded_price
            trades.append(Trade(date=date, asset=crypto_asset, type="buy",
                                amount=crypto_amount, price=price, fee=0.0))
            special_events.append(SpecialEvent(date=date, asset=crypto_asset,
                                               event_type=tx_type, amount=crypto_amount,
                                               price=price, fee=0.0, notes=""))

        # ── "out": withdrawal to external wallet ─────────────────────────────
        # NOT a taxable disposal — SpecialEvent only, NEVER a SELL trade.
        elif tx_type == "out":
            if origin_asset and origin_amount > 0 and not _is_fiat(origin_asset):
                special_events.append(SpecialEvent(
                    date=date, asset=origin_asset, event_type="withdrawal",
                    amount=origin_amount, price=0.0, fee=fee_amount,
                    notes="transfer to external wallet — not a taxable disposal",
                ))
