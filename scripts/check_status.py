import asyncio
import httpx

async def main():
    async with httpx.AsyncClient(trust_env=False, timeout=10.0) as c:
        headers = {"X-User-ID": "z00881489"}
        
        # Reset first
        r = await c.post("http://localhost:8080/api/houses/init", headers=headers)
        print("init:", r.status_code)
        
        # Check initial status
        r = await c.get("http://localhost:8080/api/houses/HF_26", headers=headers)
        d = r.json()
        print("initial status:", repr(d.get("data", {}).get("status", "")))
        
        # Rent it
        r = await c.post("http://localhost:8080/api/houses/HF_26/rent", 
                         headers=headers,
                         params={"listing_platform": "安居客"})
        print("rent:", r.status_code, r.text[:200])
        
        # Check after rent
        r = await c.get("http://localhost:8080/api/houses/HF_26", headers=headers)
        d = r.json()
        print("after rent status:", repr(d.get("data", {}).get("status", "")))
        
        # Offline
        r2 = await c.post("http://localhost:8080/api/houses/HF_150/offline",
                          headers=headers,
                          params={"listing_platform": "安居客"})
        print("offline:", r2.status_code, r2.text[:200])
        
        r3 = await c.get("http://localhost:8080/api/houses/HF_150", headers=headers)
        d3 = r3.json()
        print("after offline status:", repr(d3.get("data", {}).get("status", "")))
        
        # Terminate
        r4 = await c.post("http://localhost:8080/api/houses/HF_26/terminate",
                          headers=headers)
        print("terminate:", r4.status_code, r4.text[:200])
        
        r5 = await c.get("http://localhost:8080/api/houses/HF_26", headers=headers)
        d5 = r5.json()
        print("after terminate status:", repr(d5.get("data", {}).get("status", "")))

asyncio.run(main())
