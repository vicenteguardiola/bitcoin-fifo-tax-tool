from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple


class PriceLoader:
    """Load and manage historic cryptocurrency prices from CSV files."""

    def __init__(self):
        """Initialize price loader with empty price database."""
        # Structure: {asset: {date: price}}
        self.prices: Dict[str, Dict[str, float]] = {}

    def load_from_csv(self, path: str | Path, asset: str | None = None) -> None:
        """
        Load prices from a CoinMarketCap CSV file.
        
        Args:
            path: Path to the CSV file
            asset: Asset symbol (e.g., 'BTC', 'ETH'). If None, extracted from filename.
        
        Expected CSV format (CoinMarketCap daily OHLC):
        timeOpen;timeClose;timeHigh;timeLow;name;open;high;low;close;volume;marketCap;circulatingSupply;timestamp
        """
        path = Path(path)
        
        # Extract asset from filename if not provided
        if asset is None:
            # Filename format: 2025_historical_data_coinmarketcap_BTC.csv
            parts = path.stem.split("_")
            if len(parts) >= 5:
                asset = parts[-1].upper()
            else:
                raise ValueError(f"Could not extract asset from filename: {path.name}")
        
        asset = asset.upper()
        
        if asset not in self.prices:
            self.prices[asset] = {}
        
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            # CoinMarketCap uses semicolon delimiter
            reader = csv.DictReader(f, delimiter=";")
            
            if reader.fieldnames is None:
                raise ValueError(f"Could not read CSV header from {path}")
            
            for row in reader:
                if not row:
                    continue
                
                try:
                    # Parse the timestamp field (ISO 8601 format)
                    timestamp_str = row.get("timestamp", "").strip()
                    if not timestamp_str:
                        continue
                    
                    # Extract just the date part (YYYY-MM-DD)
                    date_obj = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    date_key = date_obj.strftime("%Y-%m-%d")
                    
                    # Get the closing price
                    close_price_str = row.get("close", "").strip()
                    if not close_price_str:
                        continue
                    
                    close_price = float(close_price_str)
                    self.prices[asset][date_key] = close_price
                    
                except (ValueError, KeyError) as e:
                    # Skip malformed rows
                    continue
    
    def load_from_directory(self, directory: str | Path) -> None:
        """
        Load all CSV files from a directory.
        
        Expected filename format: *_ASSET.csv (e.g., 2025_historical_data_coinmarketcap_BTC.csv)
        """
        directory = Path(directory)
        
        for csv_file in directory.glob("*.csv"):
            try:
                self.load_from_csv(csv_file)
            except ValueError as e:
                print(f"Skipping {csv_file}: {e}")
    
    def get_price(
        self, asset: str, date: datetime, use_nearest: bool = True
    ) -> Optional[float]:
        """
        Get price for an asset on a specific date.
        
        Args:
            asset: Asset symbol (e.g., 'BTC', 'ETH')
            date: Transaction date
            use_nearest: If exact date not found, use nearest date within 7 days
        
        Returns:
            Price in EUR, or None if not found
        """
        asset = asset.upper()
        
        if asset not in self.prices:
            return None
        
        date_key = date.strftime("%Y-%m-%d")
        
        # Try exact date match
        if date_key in self.prices[asset]:
            return self.prices[asset][date_key]
        
        # If not found and use_nearest is True, find closest date
        if use_nearest:
            return self._find_nearest_price(asset, date)
        
        return None
    
    def _find_nearest_price(self, asset: str, date: datetime, max_days: int = 7) -> Optional[float]:
        """Find the closest price within max_days."""
        asset_prices = self.prices[asset]
        
        # Search forward and backward
        for days_offset in range(1, max_days + 1):
            # Try earlier date
            earlier = date - timedelta(days=days_offset)
            earlier_key = earlier.strftime("%Y-%m-%d")
            if earlier_key in asset_prices:
                return asset_prices[earlier_key]
            
            # Try later date
            later = date + timedelta(days=days_offset)
            later_key = later.strftime("%Y-%m-%d")
            if later_key in asset_prices:
                return asset_prices[later_key]
        
        return None
    
    def has_asset(self, asset: str) -> bool:
        """Check if we have price data for an asset."""
        return asset.upper() in self.prices
    
    def assets(self) -> list[str]:
        """Get list of available assets."""
        return list(self.prices.keys())
    
    def price_range(self, asset: str) -> Tuple[Optional[str], Optional[str]]:
        """Get the date range of available prices for an asset."""
        asset = asset.upper()
        if asset not in self.prices or not self.prices[asset]:
            return None, None
        
        dates = sorted(self.prices[asset].keys())
        return dates[0], dates[-1]
