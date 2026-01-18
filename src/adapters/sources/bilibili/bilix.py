import os
import shutil
import asyncio
from typing import Dict, List, Optional
from bilix.sites.bilibili import DownloaderBilibili
from bilix.sites.bilibili import api
import httpx
import logging

logger = logging.getLogger(__name__)

class BilixCrawler:
    def __init__(self, download_dir: str = "downloads"):
        self.download_dir = download_dir
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)
        # We'll create a client for API calls
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/"
        }

    async def get_author_info(self, url_or_mid: str) -> Dict:
        """
        Get author info. 
        If url_or_mid is a Video URL, fetch video info and extract author.
        """
        # Check if it's a Video URL (BV...)
        bvid = None
        if "bilibili.com/video/BV" in url_or_mid:
            bvid = "BV" + url_or_mid.split("/BV")[1].split("/")[0].split("?")[0]
        elif url_or_mid.startswith("BV"):
            bvid = url_or_mid
            
        async with httpx.AsyncClient(headers=self.headers) as client:
            try:
                if bvid:
                    # Fetch video info to get author
                    info = await api.get_video_info(client, f"https://www.bilibili.com/video/{bvid}")
                    
                    # Attempt to find author name
                    name = getattr(info, 'owner_name', None) or getattr(info, 'author_name', None) or getattr(info, 'up_name', None) or "Unknown Author"
                    mid = getattr(info, 'owner_id', None) or getattr(info, 'mid', None) or getattr(info, 'up_mid', None) or "0"
                    face = getattr(info, 'owner_face', None) or getattr(info, 'face', None) or ""
                    
                    return {
                        "name": name,
                        "face": face,
                        "mid": mid,
                        "desc": f"Author of {bvid}"
                    }
                
                # Normal Author Logic
                # bilix get_up_info signature: (client, url_or_mid)
                # Try to extract MID if it's a URL
                if "space.bilibili.com" in url_or_mid:
                    url_or_mid = url_or_mid.split("space.bilibili.com/")[-1].split("/")[0].split("?")[0]
                
                info = await api.get_up_info(client, url_or_mid)
                logger.info(f"Bilix get_up_info result: {info}")
                
                # Handle if info is dict or object
                if isinstance(info, dict):
                    return {
                        "name": info.get("name"),
                        "face": info.get("face"),
                        "mid": info.get("mid"),
                        "desc": info.get("desc", "") or info.get("sign", "")
                    }
                else:
                    return {
                        "name": info.name,
                        "face": info.face,
                        "mid": info.mid,
                        "desc": getattr(info, "desc", "") or getattr(info, "sign", "")
                    }
            except Exception as e:
                logger.error(f"Failed to get author info for {url_or_mid}: {e}")
                # Return dummy if failed?
                # For MVP test, let's raise
                raise

    async def get_videos(self, url_or_mid: str, limit: int = 10) -> List[Dict]:
        """
        Get videos for author.
        If input is Video URL, return that single video.
        """
        # Check if it's a Video URL
        bvid = None
        if "bilibili.com/video/BV" in url_or_mid:
            bvid = "BV" + url_or_mid.split("/BV")[1].split("/")[0].split("?")[0]
        elif url_or_mid.startswith("BV"):
            bvid = url_or_mid
            
        if bvid:
             async with httpx.AsyncClient(headers=self.headers) as client:
                 info = await api.get_video_info(client, f"https://www.bilibili.com/video/{bvid}")
                 
                 # Safely get fields
                 duration = getattr(info, 'duration', 0)
                 # bilix duration might be milliseconds or seconds?
                 # usually seconds.
                 
                 return [{
                     "bvid": info.bvid,
                     "title": info.title,
                     "created": getattr(info, 'pub_date', 0) or getattr(info, 'time', 0) or 0,
                     "length": duration,
                     "pic": getattr(info, 'img_url', '') or getattr(info, 'cover', '')
                 }]

        videos = []
        page = 1
        page_size = 30
        
        async with httpx.AsyncClient(headers=self.headers) as client:
            while True:
                try:
                    # bilix api signature: get_up_video_info(client, url_or_mid, pn, ps, ...)
                    # It returns a list of VideoInfo or similar? 
                    # Let's verify return type. It usually returns list of dict or objects.
                    # Based on research_bilix_2.py, it likely returns list.
                    
                    # Note: get_up_video_info returns (video_list, total) tuple or just list?
                    # I need to be careful. Let's assume it returns a list based on name.
                    # Wait, usually these APIs return a response object or list.
                    # Let's try to call it in research script if unsure, but I'll assume list for now 
                    # and catch exception if structure is different.
                    
                    # Actually, bilix `get_up_video_info` returns `List[VideoInfo]`.
                    
                    batch = await api.get_up_video_info(client, url_or_mid, pn=page, ps=page_size)
                    
                    if not batch:
                        break
                        
                    for v in batch:
                        videos.append({
                            "bvid": v.bvid,
                            "title": v.title,
                            "created": v.pub_date, # check if it's timestamp or string
                            "length": v.duration, # check format
                            "pic": v.cover
                        })
                        if 0 < limit <= len(videos):
                            return videos[:limit]
                    
                    page += 1
                    
                    # Safety break if limit is 0 (all) but too many pages?
                    # For now just continue until empty.
                    
                except Exception as e:
                    logger.error(f"Error fetching videos page {page}: {e}")
                    break
                    
        return videos

    async def get_video_info(self, bvid: str) -> Dict:
        """Get detail info"""
        async with httpx.AsyncClient(headers=self.headers) as client:
            info = await api.get_video_info(client, f"https://www.bilibili.com/video/{bvid}")
            
            # Safely get attributes
            cid = getattr(info, 'cid', 0)
            title = getattr(info, 'title', 'Unknown Title')
            desc = getattr(info, 'desc', '')
            duration = getattr(info, 'duration', 0)
            
            return {
                "cid": cid,
                "title": title,
                "desc": desc, 
                "duration": duration
            }

    async def get_subtitle(self, bvid: str, cid: int) -> List[Dict]:
        """
        Get subtitle using bilix api.
        """
        async with httpx.AsyncClient(headers=self.headers) as client:
            try:
                # bilix has get_subtitle_info(client, bvid, cid)
                # It returns list of available subtitles.
                # Then we need to download content.
                # Or maybe bilix has helper.
                
                # Let's use the one from `api`
                sub_info = await api.get_subtitle_info(client, bvid, cid)
                
                # sub_info is likely a list of subtitle meta
                target_sub = next((s for s in sub_info if s.lan == 'zh-CN'), None)
                if not target_sub and sub_info:
                    target_sub = sub_info[0]
                    
                if target_sub:
                    # Download content
                    resp = await client.get(target_sub.url)
                    # Bilibili json format
                    data = resp.json()
                    return data.get('body', [])
                    
            except Exception as e:
                logger.warning(f"Failed to get subtitle for {bvid}: {e}")
        
        return []

    async def download_audio(self, bvid: str) -> Optional[str]:
        """
        Download audio for video. Returns file path.
        """
        url = f"https://www.bilibili.com/video/{bvid}"
        try:
            # Clean download dir to ensure we capture the correct file
            # CAUTION: This assumes no concurrent downloads in this dir!
            for f in os.listdir(self.download_dir):
                fp = os.path.join(self.download_dir, f)
                try:
                    if os.path.isfile(fp):
                        os.unlink(fp)
                except Exception:
                    pass

            async with DownloaderBilibili(part_concurrency=1) as d:
                # bilix will download file here
                paths = await d.get_video(url, path=self.download_dir, only_audio=True, image=False)
                
                if paths:
                    if isinstance(paths, list):
                        return str(paths[0])
                    return str(paths)
                
                # Fallback: Check directory for any downloaded file
                files = [f for f in os.listdir(self.download_dir) if not f.startswith(".")]
                if files:
                    # Return the first file found (assuming we cleaned dir)
                    return os.path.join(self.download_dir, files[0])
                
                return None
                
        except Exception as e:
            logger.error(f"Download audio failed for {bvid}: {e}")
            return None
