from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uvicorn
import json
import os
import sys
import httpx
import asyncio
from datetime import datetime, timedelta
import random

app = FastAPI(title="Financial MCP HTTP API")

# Request models
class StockQuoteRequest(BaseModel):
    symbol: str

class StockHistoryRequest(BaseModel):
    symbol: str
    period: str = "1mo"

class StockSearchRequest(BaseModel):
    query: str

# Copy the MOCK_STOCK_DATA from your server.py
MOCK_STOCK_DATA = {
    "AAPL": {"name": "Apple Inc.", "price": 175.50, "change": 2.30, "volume": 45_000_000, "market_cap": 2_800_000_000_000},
    "GOOGL": {"name": "Alphabet Inc. Class A", "price": 139.25, "change": -1.85, "volume": 28_000_000, "market_cap": 1_750_000_000_000},
    "MSFT": {"name": "Microsoft Corporation", "price": 378.90, "change": 4.20, "volume": 22_000_000, "market_cap": 2_900_000_000_000},
    "AMZN": {"name": "Amazon.com Inc.", "price": 142.80, "change": -0.95, "volume": 35_000_000, "market_cap": 1_500_000_000_000},
    "TSLA": {"name": "Tesla Inc.", "price": 248.50, "change": 8.75, "volume": 85_000_000, "market_cap": 790_000_000_000},
    "META": {"name": "Meta Platforms Inc.", "price": 298.35, "change": -2.15, "volume": 18_000_000, "market_cap": 750_000_000_000},
    "NVDA": {"name": "NVIDIA Corporation", "price": 875.30, "change": 15.60, "volume": 40_000_000, "market_cap": 2_100_000_000_000},
    "NFLX": {"name": "Netflix Inc.", "price": 425.70, "change": -3.45, "volume": 12_000_000, "market_cap": 185_000_000_000},
    "AMD": {"name": "Advanced Micro Devices Inc.", "price": 142.90, "change": 3.80, "volume": 38_000_000, "market_cap": 230_000_000_000},
    "CRM": {"name": "Salesforce Inc.", "price": 215.40, "change": 1.25, "volume": 8_500_000, "market_cap": 210_000_000_000}
}

# Copy transaction function from your server.py
async def get_transactions_from_backend(user_token: str = None):
    """Get transactions from the backend API instead of local file"""
    try:
        backend_url = os.getenv("BACKEND_API_URL", "http://localhost:8000")
        
        headers = {}
        if user_token:
            headers["Authorization"] = f"Bearer {user_token}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{backend_url}/user/me/transactions/mock",
                headers=headers,
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                # Extract the 'added' transactions from the response structure
                if isinstance(data, dict) and 'added' in data:
                    return {"transactions": data['added']}
                else:
                    return {"transactions": data}
            else:
                print(f"Backend API returned status {response.status_code}", file=sys.stderr)
                return get_fallback_transactions()
                
    except Exception as e:
        print(f"Error fetching transactions from backend: {e}", file=sys.stderr)
        return get_fallback_transactions()

def get_fallback_transactions():
    """Fallback to local file if backend is unavailable"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, "transaction_data.json")
    
    try:
        with open(json_path, "r") as f:
            transaction_data = json.load(f)
        print("Using fallback transaction data from local file", file=sys.stderr)
        return transaction_data
    except FileNotFoundError:
        print(f"Could not find transaction_data.json at {json_path}", file=sys.stderr)
        return {"error": "Transaction data file not found and backend unavailable"}
    except json.JSONDecodeError:
        print("Invalid JSON in transaction_data.json", file=sys.stderr)
        return {"error": "Invalid JSON format and backend unavailable"}

# Copy the real Yahoo Finance functions from your server.py
async def try_live_stock_quote(symbol: str) -> Optional[Dict[str, Any]]:
    """Try to get live stock data from multiple sources - copied from server.py"""
    
    # Try Yahoo Finance first
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5.0, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("chart", {}).get("result"):
                    result = data["chart"]["result"][0]
                    meta = result["meta"]
                    
                    current_price = meta.get("regularMarketPrice", 0)
                    previous_close = meta.get("previousClose", 0)
                    
                    if current_price > 0:  # Valid data
                        change = current_price - previous_close
                        change_percent = (change / previous_close) * 100 if previous_close else 0
                        
                        return {
                            "symbol": symbol.upper(),
                            "name": meta.get("longName", symbol.upper()),
                            "price": round(current_price, 2),
                            "change": round(change, 2),
                            "change_percent": round(change_percent, 2),
                            "previous_close": round(previous_close, 2),
                            "open": round(meta.get("regularMarketOpen", 0), 2),
                            "high": round(meta.get("regularMarketDayHigh", 0), 2),
                            "low": round(meta.get("regularMarketDayLow", 0), 2),
                            "volume": meta.get("regularMarketVolume", 0),
                            "market_cap": meta.get("marketCap", 0),
                            "currency": meta.get("currency", "USD"),
                            "exchange": meta.get("exchangeName", ""),
                            "last_updated": datetime.now().isoformat(),
                            "data_source": "yahoo_finance",
                            "status": "success"
                        }
    except Exception as e:
        print(f"Yahoo Finance API failed for {symbol}: {e}")
    
    # Try alternative API (Alpha Vantage demo endpoint)
    try:
        url = f"https://www.alphavantage.co/query"
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": "demo"  # Demo key with limited calls
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=5.0)
            
            if response.status_code == 200:
                data = response.json()
                quote = data.get("Global Quote", {})
                
                if quote and quote.get("05. price"):
                    price = float(quote.get("05. price", 0))
                    change = float(quote.get("09. change", 0))
                    change_percent = float(quote.get("10. change percent", "0%").replace("%", ""))
                    
                    return {
                        "symbol": symbol.upper(),
                        "name": f"{symbol.upper()} Inc.",
                        "price": round(price, 2),
                        "change": round(change, 2),
                        "change_percent": round(change_percent, 2),
                        "previous_close": round(price - change, 2),
                        "open": round(float(quote.get("02. open", price)), 2),
                        "high": round(float(quote.get("03. high", price)), 2),
                        "low": round(float(quote.get("04. low", price)), 2),
                        "volume": int(quote.get("06. volume", 0)),
                        "market_cap": 0,
                        "currency": "USD",
                        "exchange": "NASDAQ/NYSE",
                        "last_updated": quote.get("07. latest trading day", datetime.now().date().isoformat()),
                        "data_source": "alpha_vantage",
                        "status": "success"
                    }
    except Exception as e:
        print(f"Alpha Vantage API failed for {symbol}: {e}")
    
    return None

def get_mock_stock_quote(symbol: str) -> Dict[str, Any]:
    """Generate mock stock data for fallback - copied from server.py"""
    symbol = symbol.upper()
    
    if symbol in MOCK_STOCK_DATA:
        base_data = MOCK_STOCK_DATA[symbol].copy()
        
        # Add some random variation to make it look live
        price_variation = random.uniform(-0.02, 0.02)  # ±2% variation
        change_variation = random.uniform(-0.5, 0.5)   # ±$0.50 variation
        
        base_price = base_data["price"]
        varied_price = base_price * (1 + price_variation)
        varied_change = base_data["change"] + change_variation
        
        return {
            "symbol": symbol,
            "name": base_data["name"],
            "price": round(varied_price, 2),
            "change": round(varied_change, 2),
            "change_percent": round((varied_change / (varied_price - varied_change)) * 100, 2),
            "previous_close": round(varied_price - varied_change, 2),
            "open": round(varied_price - (varied_change * 0.3), 2),
            "high": round(varied_price + abs(varied_change * 0.7), 2),
            "low": round(varied_price - abs(varied_change * 0.8), 2),
            "volume": base_data["volume"] + random.randint(-1_000_000, 1_000_000),
            "market_cap": base_data["market_cap"],
            "currency": "USD",
            "exchange": "NASDAQ/NYSE",
            "last_updated": datetime.now().isoformat(),
            "data_source": "mock_data",
            "status": "success"
        }
    else:
        # Generate mock data for unknown symbols
        base_price = random.uniform(50, 300)
        change = random.uniform(-10, 10)
        
        return {
            "symbol": symbol,
            "name": f"{symbol} Corporation",
            "price": round(base_price, 2),
            "change": round(change, 2),
            "change_percent": round((change / (base_price - change)) * 100, 2),
            "previous_close": round(base_price - change, 2),
            "open": round(base_price - (change * 0.3), 2),
            "high": round(base_price + abs(change * 0.7), 2),
            "low": round(base_price - abs(change * 0.8), 2),
            "volume": random.randint(1_000_000, 50_000_000),
            "market_cap": random.randint(10_000_000_000, 500_000_000_000),
            "currency": "USD",
            "exchange": "NASDAQ/NYSE",
            "last_updated": datetime.now().isoformat(),
            "data_source": "mock_data",
            "status": "success"
        }

# API Endpoints
@app.get("/")
async def root():
    return {"message": "Financial MCP HTTP API", "status": "running"}

@app.get("/transactions")
async def get_transactions_endpoint(x_user_token: Optional[str] = Header(None)):
    """Get transaction data from backend API"""
    try:
        result = await get_transactions_from_backend(x_user_token)
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stock/quote")
async def stock_quote(request: StockQuoteRequest):
    """Get stock quote using real Yahoo Finance API"""
    try:
        # Try to get live data first
        live_data = await try_live_stock_quote(request.symbol)
        
        if live_data:
            print(f"✅ Got live data for {request.symbol} from {live_data['data_source']}")
            return {"data": live_data}
        
        # Fallback to mock data
        print(f"⚠️ Using mock data for {request.symbol} (live data unavailable)")
        mock_data = get_mock_stock_quote(request.symbol)
        mock_data["note"] = "Live data unavailable - showing mock data for demonstration"
        
        return {"data": mock_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stock/history")
async def stock_history(request: StockHistoryRequest):
    """Get stock history using real Yahoo Finance API"""
    try:
        # Try live data first
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{request.symbol.upper()}"
            params = {
                "range": request.period,
                "interval": "1d"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=8.0, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("chart", {}).get("result"):
                        result = data["chart"]["result"][0]
                        timestamps = result.get("timestamp", [])
                        quotes = result.get("indicators", {}).get("quote", [{}])[0]
                        
                        history = []
                        for i, timestamp in enumerate(timestamps):
                            if i < len(quotes.get("close", [])) and quotes["close"][i] is not None:
                                history.append({
                                    "date": datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d"),
                                    "open": round(quotes["open"][i] or 0, 2),
                                    "high": round(quotes["high"][i] or 0, 2),
                                    "low": round(quotes["low"][i] or 0, 2),
                                    "close": round(quotes["close"][i] or 0, 2),
                                    "volume": quotes["volume"][i] if quotes.get("volume") and quotes["volume"][i] else 0
                                })
                        
                        if history:
                            start_price = history[0]["close"]
                            end_price = history[-1]["close"]
                            total_return = ((end_price - start_price) / start_price) * 100
                            
                            print(f"✅ Got live history for {request.symbol}")
                            return {"data": {
                                "symbol": request.symbol.upper(),
                                "period": request.period,
                                "history": history,
                                "total_return_percent": round(total_return, 2),
                                "data_points": len(history),
                                "start_price": start_price,
                                "end_price": end_price,
                                "data_source": "yahoo_finance",
                                "status": "success"
                            }}
        
        except Exception as e:
            print(f"Live history data failed for {request.symbol}: {e}")
        
        # Generate mock historical data
        print(f"⚠️ Using mock historical data for {request.symbol}")
        
        # Determine number of days based on period
        days_map = {"1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}
        days = days_map.get(request.period, 30)
        
        # Get current mock quote for starting point
        current_quote = get_mock_stock_quote(request.symbol)
        start_price = current_quote["price"]
        
        history = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=days-i-1)).strftime("%Y-%m-%d")
            
            # Generate realistic price movement
            daily_change = random.uniform(-0.03, 0.03)  # ±3% daily change
            if i == 0:
                price = start_price * (1 + random.uniform(-0.1, 0.1))  # Starting variation
            else:
                price = history[-1]["close"] * (1 + daily_change)
            
            high = price * (1 + random.uniform(0, 0.02))
            low = price * (1 - random.uniform(0, 0.02))
            open_price = price * (1 + random.uniform(-0.01, 0.01))
            
            history.append({
                "date": date,
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(price, 2),
                "volume": random.randint(1_000_000, 20_000_000)
            })
        
        start_price = history[0]["close"]
        end_price = history[-1]["close"]
        total_return = ((end_price - start_price) / start_price) * 100
        
        return {"data": {
            "symbol": request.symbol.upper(),
            "period": request.period,
            "history": history,
            "total_return_percent": round(total_return, 2),
            "data_points": len(history),
            "start_price": start_price,
            "end_price": end_price,
            "data_source": "mock_data",
            "note": "Live data unavailable - showing mock data for demonstration",
            "status": "success"
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stock/search")
async def stock_search(request: StockSearchRequest):
    """Search stocks using real Yahoo Finance API"""
    try:
        # Try live search first
        try:
            url = "https://query2.finance.yahoo.com/v1/finance/search"
            params = {
                "q": request.query,
                "quotesCount": 10,
                "newsCount": 0
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=5.0, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                
                if response.status_code == 200:
                    data = response.json()
                    
                    results = []
                    for quote in data.get("quotes", []):
                        if quote.get("quoteType") in ["EQUITY", "ETF"] and len(results) < 10:
                            results.append({
                                "symbol": quote.get("symbol", ""),
                                "name": quote.get("longname", quote.get("shortname", "")),
                                "exchange": quote.get("exchange", ""),
                                "type": quote.get("quoteType", ""),
                                "sector": quote.get("sector", "")
                            })
                    
                    if results:
                        print(f"✅ Got live search results for '{request.query}'")
                        return {"data": {
                            "query": request.query,
                            "results": results,
                            "count": len(results),
                            "data_source": "yahoo_finance",
                            "status": "success"
                        }}
        
        except Exception as e:
            print(f"Live search failed: {e}")
        
        # Mock search results (fallback)
        print(f"⚠️ Using mock search results for '{request.query}'")
        mock_results = []
        query_lower = request.query.lower()
        
        # Search through mock data
        for symbol, data in MOCK_STOCK_DATA.items():
            if (query_lower in data["name"].lower() or 
                query_lower in symbol.lower()):
                mock_results.append({
                    "symbol": symbol,
                    "name": data["name"],
                    "exchange": "NASDAQ",
                    "type": "EQUITY",
                    "sector": "Technology"
                })
        
        return {"data": {
            "query": request.query,
            "results": mock_results[:10],
            "count": len(mock_results[:10]),
            "data_source": "mock_data",
            "note": "Live data unavailable - showing mock results for demonstration",
            "status": "success"
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)