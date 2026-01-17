import httpx
import asyncio
from typing import List, Dict, Optional
# from bilibili_api import user, video, sync, Credential
import logging
import ssl
import certifi
import os
import time

logger = logging.getLogger(__name__)

# Force env var for requests/aiohttp
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# NOTE: Since bilibili_api (based on aiohttp) has persistent SSL issues on this environment even with patching,
# we are falling back to `httpx` (which works fine usually) and implementing the API calls manually for MVP.
# We will mimic the necessary API calls.

import hashlib
import urllib.parse
import time
import requests

# ... (Previous imports)

class BilibiliCrawler:
    def __init__(self, sessdata: str = None):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            "Cookie": f"SESSDATA={sessdata}" if sessdata else ""
        }
        self.mixin_key_enc_tab = [
            46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
            33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
            61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
            36, 20, 34, 44, 52
        ]

    async def _request(self, method, url, params=None):
        """Wrapper to run requests in executor"""
        loop = asyncio.get_event_loop()
        def sync_req():
            time.sleep(1)
            # Try a simpler User-Agent or update it
            headers = self.headers.copy()
            # headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
            
            with requests.Session() as s:
                 return s.request(method, url, params=params, headers=headers, verify=False)
        return await loop.run_in_executor(None, sync_req)


    def get_mixin_key(self, orig: str):
        """Generate mixin key"""
        return "".join([orig[i] for i in self.mixin_key_enc_tab])[:32]

    def enc_wbi(self, params: dict, img_key: str, sub_key: str):
        """Sign params with WBI"""
        mixin_key = self.get_mixin_key(img_key + sub_key)
        curr_time = round(time.time())
        params['wts'] = curr_time
        params = dict(sorted(params.items()))
        # Filter invalid chars
        params = {
            k: "".join(filter(lambda x: x not in "!'()*", str(v)))
            for k, v in params.items()
        }
        query = urllib.parse.urlencode(params)
        wbi_sign = hashlib.md5((query + mixin_key).encode()).hexdigest()
        params['w_rid'] = wbi_sign
        return params

    async def get_wbi_keys(self):
        """Get WBI keys from nav"""
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get("https://api.bilibili.com/x/web-interface/nav", headers=self.headers)
            data = resp.json()
            if data["code"] != 0:
                 # Fallback hardcoded keys might work temporarily but risky
                 return None, None
            wbi_img = data["data"]["wbi_img"]
            img_key = wbi_img["img_url"].split("/")[-1].split(".")[0]
            sub_key = wbi_img["sub_url"].split("/")[-1].split(".")[0]
            return img_key, sub_key

    async def get_author_info(self, mid: str) -> Dict:
        """Get user info by mid (user id) - WBI Signed"""
        # Note: /x/space/acc/info usually needs WBI now or at least proper headers
        # But let's try /x/space/wbi/acc/info with signature
        url = "https://api.bilibili.com/x/space/wbi/acc/info"
        
        try:
            img_key, sub_key = await self.get_wbi_keys()
        except:
            img_key, sub_key = None, None
            
        if not img_key:
             # Try fallback to simple endpoint without WBI if nav failed
             # But first sleep a bit to avoid frequency limit
             await asyncio.sleep(1)
             return await self.get_author_info_fallback(mid)
             
        params = {"mid": mid}
        signed_params = self.enc_wbi(params, img_key, sub_key)
        
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    resp = await client.get(url, params=signed_params, headers=self.headers)
                    data = resp.json()
                    if data["code"] == 0:
                        return data["data"]
                    elif data["code"] == -412: # Anti-crawler
                        logger.warning(f"Bilibili Anti-Crawler (-412). Sleep & Retry {attempt}")
                        await asyncio.sleep(3 + attempt * 2)
                        continue
                        
                    logger.warning(f"API Error {data['code']}: {data.get('message')}")
            except Exception as e:
                logger.warning(f"Request failed: {e}")
            await asyncio.sleep(1)
            
        # If WBI failed, try fallback
        return await self.get_author_info_fallback(mid)

    async def get_author_info_fallback(self, mid: str):
         # Try web interface card instead of space info (sometimes easier)
         url = "https://api.bilibili.com/x/web-interface/card"
         params = {"mid": mid}
         await asyncio.sleep(1)
         
         for attempt in range(3):
            resp = await self._request("GET", url, params=params)
            data = resp.json()
            if data["code"] == 0: 
                # Convert card data to expected format
                card = data["data"]["card"]
                return {
                    "name": card["name"],
                    "face": card["face"],
                    "mid": card["mid"]
                }
            
            if data["code"] == -412:
                 await asyncio.sleep(2)
                 continue
                 
            await asyncio.sleep(1)

         raise Exception(f"Fallback info failed: {data.get('message')}")

    async def get_videos(self, mid: str, page: int = 1, page_size: int = 30) -> Dict:
        """Get user videos - WBI Signed"""
        url = "https://api.bilibili.com/x/space/wbi/arc/search"
        
        img_key, sub_key = await self.get_wbi_keys()
        
        params = {
            "mid": mid,
            "ps": page_size,
            "tid": 0,
            "pn": page,
            "order": "pubdate"
        }
        
        if img_key:
            signed_params = self.enc_wbi(params, img_key, sub_key)
        else:
            signed_params = params # Try without if key fetch failed
            
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(url, params=signed_params, headers=self.headers)
            data = resp.json()
            if data["code"] == 0:
                return data["data"]["list"]["vlist"]
            raise Exception(f"Failed to get videos: {data.get('message')}")

    async def get_video_info(self, bvid: str) -> Dict:
        """Get video detail including cid"""
        url = "https://api.bilibili.com/x/web-interface/view"
        params = {"bvid": bvid}
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(url, params=params, headers=self.headers)
            data = resp.json()
            if data["code"] != 0:
                 raise Exception(f"Failed to get video info: {data.get('message')}")
            return data["data"]

    async def get_subtitle(self, bvid: str, cid: int) -> List[Dict]:
        """Get subtitle url and content"""
        # First get available subtitles
        url = "https://api.bilibili.com/x/player/v2"
        params = {"bvid": bvid, "cid": cid}
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(url, params=params, headers=self.headers)
            data = resp.json()
            
            # Note: /x/player/v2 might return different structure or be empty without cookie
            subtitles = data.get("data", {}).get("subtitle", {}).get("subtitles", [])
            if not subtitles:
                # Try web interface view which sometimes has subtitle info
                # But usually player v2 is the way.
                return []
            
            # Prefer zh-CN
            target_sub = next((s for s in subtitles if s["lan"] == "zh-CN"), subtitles[0])
            sub_url = target_sub["subtitle_url"]
            if sub_url.startswith("//"):
                sub_url = "https:" + sub_url
            
            # Download subtitle content (JSON format usually)
            sub_resp = await client.get(sub_url, headers=self.headers)
            return sub_resp.json().get("body", [])


# Example Usage
if __name__ == "__main__":
    crawler = BilibiliCrawler()
    # Test logic would go here
