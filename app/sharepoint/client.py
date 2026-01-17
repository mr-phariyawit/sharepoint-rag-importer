# app/sharepoint/client.py
"""SharePoint/OneDrive client using Microsoft Graph API"""

import httpx
from msal import ConfidentialClientApplication
from typing import List, Optional, Dict, Any, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse, unquote
import asyncio
import logging
import base64
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

logger = logging.getLogger(__name__)


def extract_tenant_from_url(url: str) -> str:
    """
    Extract tenant domain from SharePoint URL for Azure AD authentication.

    Azure AD accepts domain names as tenant identifiers, so we can use
    the tenant's onmicrosoft.com domain directly.

    Examples:
        - https://contoso.sharepoint.com/sites/HR → contoso.onmicrosoft.com
        - https://contoso-my.sharepoint.com/personal/user → contoso.onmicrosoft.com
        - https://apollodemo118.sharepoint.com/sites/admin → apollodemo118.onmicrosoft.com

    Args:
        url: SharePoint or OneDrive URL

    Returns:
        Tenant domain in format: {tenant}.onmicrosoft.com

    Raises:
        ValueError: If URL is not a valid SharePoint URL
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if not host:
        raise ValueError(f"Invalid URL: {url}")

    # Handle: contoso.sharepoint.com or contoso-my.sharepoint.com
    if '.sharepoint.com' in host:
        # Extract tenant name (everything before .sharepoint.com)
        tenant = host.split('.sharepoint.com')[0]
        # Remove OneDrive suffix (-my)
        tenant = tenant.replace('-my', '')
        return f"{tenant}.onmicrosoft.com"

    raise ValueError(
        f"Invalid SharePoint URL: {url}. "
        "URL must contain .sharepoint.com domain."
    )


@dataclass
class SharePointFile:
    """Represents a file from SharePoint/OneDrive"""
    id: str
    name: str
    path: str
    mime_type: str
    size_bytes: int
    web_url: str
    drive_id: str
    site_id: Optional[str] = None
    parent_id: Optional[str] = None
    etag: Optional[str] = None
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    created_by: Optional[str] = None
    modified_by: Optional[str] = None
    download_url: Optional[str] = None
    content_hash: Optional[str] = None


@dataclass
class SharePointFolder:
    """Represents a folder from SharePoint/OneDrive"""
    id: str
    name: str
    path: str
    web_url: str
    drive_id: str
    site_id: Optional[str] = None
    child_count: int = 0


@dataclass
class CrawlProgress:
    """Progress tracking for folder crawl"""
    total_folders_found: int = 0
    total_files_found: int = 0
    folders_processed: int = 0
    current_folder: str = ""
    files: List[SharePointFile] = field(default_factory=list)


class SharePointClient:
    """
    SharePoint/OneDrive client using Microsoft Graph API.
    Supports recursive folder traversal.
    """
    
    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
    SCOPES = ["https://graph.microsoft.com/.default"]
    
    # Supported file extensions
    SUPPORTED_EXTENSIONS = {
        '.pdf', '.docx', '.doc', '.xlsx', '.xls',
        '.pptx', '.ppt', '.txt', '.csv', '.md',
        '.html', '.htm', '.json', '.xml',
        '.png', '.jpg', '.jpeg'
    }
    
    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        supported_extensions: Optional[set] = None
    ):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.supported_extensions = supported_extensions or self.SUPPORTED_EXTENSIONS
        
        self._app = None
        self._access_token = None
        self._client = None
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def authenticate(self) -> bool:
        """Authenticate with Microsoft Graph API using client credentials"""
        try:
            self._app = ConfidentialClientApplication(
                self.client_id,
                authority=f"https://login.microsoftonline.com/{self.tenant_id}",
                client_credential=self.client_secret
            )
            
            result = self._app.acquire_token_for_client(scopes=self.SCOPES)
            
            if "access_token" in result:
                self._access_token = result["access_token"]
                self._client = httpx.AsyncClient(
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    timeout=60.0,
                    follow_redirects=True
                )
                logger.info("✅ SharePoint authentication successful")
                return True
            else:
                error = result.get("error_description", "Unknown error")
                logger.error(f"❌ Authentication failed: {error}")
                raise Exception(f"Authentication failed: {error}")
                
        except Exception as e:
            logger.error(f"❌ Authentication error: {e}")
            raise
    
    async def close(self):
        """Close the HTTP client"""
        if self._client:
            await self._client.aclose()
    
    def parse_sharepoint_url(self, url: str) -> Dict[str, str]:
        """
        Parse SharePoint URL to extract site, drive, and folder info.
        
        Supports formats:
        - https://company.sharepoint.com/sites/MySite/Shared Documents/Folder
        - https://company.sharepoint.com/:f:/s/MySite/xxx
        - https://company-my.sharepoint.com/personal/user/Documents/Folder
        """
        parsed = urlparse(url)
        path_parts = unquote(parsed.path).split('/')
        
        result = {
            "host": parsed.netloc,
            "site_path": None,
            "drive_name": None,
            "folder_path": None
        }
        
        # SharePoint site URL
        if '/sites/' in parsed.path:
            site_idx = path_parts.index('sites')
            result["site_path"] = f"/sites/{path_parts[site_idx + 1]}"
            
            # Find drive (usually "Shared Documents" or custom library)
            remaining = path_parts[site_idx + 2:]
            if remaining:
                result["drive_name"] = remaining[0]
                result["folder_path"] = '/'.join(remaining[1:]) if len(remaining) > 1 else ""
        
        # OneDrive personal
        elif '/personal/' in parsed.path:
            personal_idx = path_parts.index('personal')
            result["site_path"] = f"/personal/{path_parts[personal_idx + 1]}"
            remaining = path_parts[personal_idx + 2:]
            if remaining:
                result["drive_name"] = remaining[0]
                result["folder_path"] = '/'.join(remaining[1:]) if len(remaining) > 1 else ""
        
        return result

    async def resolve_sharing_url(self, url: str) -> Dict[str, Any]:
        """
        Resolve a sharing URL to a DriveItem.
        """
        # Encode URL according to MS Graph spec
        # 1. Base64 encode
        b64 = base64.b64encode(url.encode()).decode()
        # 2. Replace chars
        encoded = "u!" + b64.rstrip('=').replace('/', '_').replace('+', '-')
        
        try:
            response = await self._client.get(
                f"{self.GRAPH_BASE_URL}/shares/{encoded}/driveItem"
            )
            response.raise_for_status()
            item = response.json()
            
            # Enrich with site info if possible (Sharing links don't always give siteId directly)
            # Item has parentReference usually
            return item
        except Exception as e:
            logger.error(f"Failed to resolve sharing URL: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def get_site_and_drive(self, url: str) -> tuple[str, str, str]:
        """
        Get site ID and drive ID from SharePoint URL.
        Returns: (site_id, drive_id, folder_path)
        """
        url_info = self.parse_sharepoint_url(url)
        
        # Get site ID
        site_path = url_info["site_path"]
        host = url_info["host"]
        
        site_response = await self._client.get(
            f"{self.GRAPH_BASE_URL}/sites/{host}:{site_path}"
        )
        site_response.raise_for_status()
        site_data = site_response.json()
        site_id = site_data["id"]
        
        # Get drive ID
        drives_response = await self._client.get(
            f"{self.GRAPH_BASE_URL}/sites/{site_id}/drives"
        )
        drives_response.raise_for_status()
        drives_data = drives_response.json()
        
        # Find matching drive
        drive_name = url_info.get("drive_name", "Documents")
        drive_id = None
        
        for drive in drives_data.get("value", []):
            if drive["name"] == drive_name or drive_name in drive["name"]:
                drive_id = drive["id"]
                break
        
        if not drive_id and drives_data.get("value"):
            # Fallback to first drive
            drive_id = drives_data["value"][0]["id"]
        
        folder_path = url_info.get("folder_path", "")
        
        logger.info(f"📍 Site: {site_id}, Drive: {drive_id}, Path: /{folder_path}")
        
        return site_id, drive_id, folder_path
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def list_drives(self, site_id: str = "root") -> List[Dict[str, Any]]:
        """List drives (document libraries) for a site"""
        try:
            response = await self._client.get(
                f"{self.GRAPH_BASE_URL}/sites/{site_id}/drives"
            )
            response.raise_for_status()
            data = response.json()
            return data.get("value", [])
        except Exception as e:
            logger.error(f"Failed to list drives for site {site_id}: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def get_folder_id(
        self, 
        drive_id: str, 
        folder_path: str
    ) -> Optional[str]:
        """Get folder ID from path"""
        if not folder_path or folder_path == "/":
            return "root"
        
        # Clean path
        folder_path = folder_path.strip("/")
        
        try:
            response = await self._client.get(
                f"{self.GRAPH_BASE_URL}/drives/{drive_id}/root:/{folder_path}"
            )
            response.raise_for_status()
            data = response.json()
            return data["id"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Folder not found: {folder_path}")
                return None
            raise
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def list_folder_contents(
        self,
        drive_id: str,
        folder_id: str = "root",
        page_size: int = 200
    ) -> tuple[List[SharePointFile], List[SharePointFolder]]:
        """
        List all files and subfolders in a folder.
        """
        files = []
        folders = []
        
        url = f"{self.GRAPH_BASE_URL}/drives/{drive_id}/items/{folder_id}/children"
        params = {
            "$top": page_size,
            "$select": "id,name,file,folder,size,webUrl,parentReference,"
                      "createdDateTime,lastModifiedDateTime,createdBy,"
                      "lastModifiedBy,@microsoft.graph.downloadUrl,eTag"
        }
        
        while url:
            # We retry the individual page fetch
            try:
                response = await self._client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                for item in data.get("value", []):
                    if "folder" in item:
                        # It's a folder
                        folders.append(SharePointFolder(
                            id=item["id"],
                            name=item["name"],
                            path=item.get("parentReference", {}).get("path", "") + "/" + item["name"],
                            web_url=item.get("webUrl", ""),
                            drive_id=drive_id,
                            child_count=item.get("folder", {}).get("childCount", 0)
                        ))
                    elif "file" in item:
                        # It's a file - check extension
                        name = item["name"]
                        ext = '.' + name.rsplit('.', 1)[-1].lower() if '.' in name else ''
                        
                        if ext in self.supported_extensions:
                            files.append(SharePointFile(
                                id=item["id"],
                                name=name,
                                path=item.get("parentReference", {}).get("path", "") + "/" + name,
                                mime_type=item.get("file", {}).get("mimeType", "application/octet-stream"),
                                size_bytes=item.get("size", 0),
                                web_url=item.get("webUrl", ""),
                                drive_id=drive_id,
                                etag=item.get("eTag"),
                                created_at=self._parse_datetime(item.get("createdDateTime")),
                                modified_at=self._parse_datetime(item.get("lastModifiedDateTime")),
                                created_by=item.get("createdBy", {}).get("user", {}).get("email"),
                                modified_by=item.get("lastModifiedBy", {}).get("user", {}).get("email"),
                                download_url=item.get("@microsoft.graph.downloadUrl"),
                                content_hash=item.get("file", {}).get("hashes", {}).get("sha256Hash")
                            ))
                
                # Check for next page
                url = data.get("@odata.nextLink")
                params = {}  # Params are included in nextLink
                
            except httpx.HTTPStatusError as e:
                # If we get a 429, we definitely want to retry (handled by decorator)
                logger.warning(f"Http Error during list_folder_contents: {e}")
                raise
        
        return files, folders
    
    async def crawl_folder_recursive(
        self,
        drive_id: str,
        folder_id: str = "root",
        site_id: Optional[str] = None,
        max_depth: int = 50,
        progress_callback: Optional[callable] = None
    ) -> AsyncIterator[SharePointFile]:
        """
        Recursively crawl folder and yield all files.
        
        Args:
            drive_id: SharePoint drive ID
            folder_id: Starting folder ID (default: root)
            site_id: Optional site ID for metadata
            max_depth: Maximum recursion depth
            progress_callback: Optional callback for progress updates
        
        Yields:
            SharePointFile objects
        """
        progress = CrawlProgress()
        
        async def crawl(fid: str, depth: int, path: str):
            if depth > max_depth:
                logger.warning(f"⚠️ Max depth reached at {path}")
                return
            
            progress.current_folder = path
            
            try:
                files, folders = await self.list_folder_contents(drive_id, fid)
                
                progress.total_files_found += len(files)
                progress.total_folders_found += len(folders)
                
                # Yield files
                for file in files:
                    file.site_id = site_id
                    yield file
                
                # Process subfolders
                for folder in folders:
                    progress.folders_processed += 1
                    
                    if progress_callback:
                        progress_callback(progress)
                    
                    logger.info(f"📂 Entering: {folder.path} ({folder.child_count} items)")
                    
                    async for file in crawl(folder.id, depth + 1, folder.path):
                        yield file
                        
            except Exception as e:
                logger.error(f"❌ Error crawling {path}: {e}")
        
        logger.info(f"🔍 Starting recursive crawl from folder {folder_id}")
        
        async for file in crawl(folder_id, 0, "/"):
            yield file
        
        logger.info(
            f"✅ Crawl complete: {progress.total_files_found} files in "
            f"{progress.total_folders_found} folders"
        )
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=30),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    async def download_file(self, file: SharePointFile) -> bytes:
        """Download file content"""
        if file.download_url:
            # Use pre-authenticated download URL
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.get(file.download_url)
                response.raise_for_status()
                return response.content
        else:
            # Fallback to Graph API
            response = await self._client.get(
                f"{self.GRAPH_BASE_URL}/drives/{file.drive_id}/items/{file.id}/content"
            )
            response.raise_for_status()
            return response.content
    
    async def get_file_content_stream(
        self, 
        file: SharePointFile,
        chunk_size: int = 1024 * 1024  # 1MB chunks
    ) -> AsyncIterator[bytes]:
        """Stream file content for large files"""
        url = file.download_url or f"{self.GRAPH_BASE_URL}/drives/{file.drive_id}/items/{file.id}/content"
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size):
                    yield chunk
    
    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string"""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except:
            return None
    
    async def validate_connection(self) -> Dict[str, Any]:
        """Validate connection and return user info"""
        try:
            # We don't retry this one as it's a quick check
            response = await self._client.get(f"{self.GRAPH_BASE_URL}/me")
            if response.status_code == 200:
                user = response.json()
                return {
                    "valid": True,
                    "user": user.get("displayName"),
                    "email": user.get("mail") or user.get("userPrincipalName")
                }
        except:
            pass
        
        # For app-only auth, check organization
        try:
            response = await self._client.get(f"{self.GRAPH_BASE_URL}/organization")
            if response.status_code == 200:
                org = response.json().get("value", [{}])[0]
                return {
                    "valid": True,
                    "organization": org.get("displayName"),
                    "tenant_id": org.get("id")
                }
        except:
            pass
            
        # Fallback: Check root site (requires Sites.Read.All)
        try:
            response = await self._client.get(f"{self.GRAPH_BASE_URL}/sites/root")
            if response.status_code == 200:
                site = response.json()
                return {
                    "valid": True,
                    "site": site.get("name"),
                    "web_url": site.get("webUrl")
                }
        except:
            pass
        
        return {"valid": False}
