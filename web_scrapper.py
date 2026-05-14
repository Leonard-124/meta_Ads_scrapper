

import requests, time, json, csv, logging, random
from typing import List, Dict, Optional  

#Meta Ads access_token configuration
ACCESS_TOKEN = "EAAOCXeAhE7cBRbcIUNG35eUB2aGfGttBk46ZAOYC9QNXr1xoubZCS4Xx6I5hdq7vs11Wz4C8zOtwpMgHYRuZC2ZBYUQFEZBl7N0HEpyvYDZAbmwdZAfO3wsyPbKawaS2ITGvh7i3IF5TTg3sqsrDAUZC7UFnhz3dnVOjZC4tZBEg6QRM20YqGRDd95y59xwZCDOObfambHw7rZBZB15t3ZBAG0WuHg3UrtIxZBInHGGlfcVEWUwGADbL15iw6clC2Yx3zWsO087BTPIZCFhLPjVtlDpmQPssjTpt"

edge_all_open_tabs = [ # This is edge tab metadata, helper extracts slug from this data
    {"pageTitle":"<WebsiteContent_fRRRFBo78Ad1TfNtd1jje>scrapy/docs at master \u00B7 scrapy/scrapy \u00B7 GitHub</WebsiteContent_fRRRFBo78Ad1TfNtd1jje>",
     "pageUrl":"<WebsiteContent_fRRRFBo78Ad1TfNtd1jje>https://github.com/scrapy/scrapy/tree/master/docs</WebsiteContent_fRRRFBo78Ad1TfNtd1jje>",
     "tabId":1282741773,"isCurrent":True} 
]

API_BASE = "https://graph.facebook.com/v18.0/ads_archive" #endpoint for ad query
DEFAULT_COUNTRIES = ["KE"]
FIELDS = ( #ad field request from API
    "ad_creation_time,ad_creative_body,ad_creative_link_caption,"
    "ad_creative_link_description,ad_creative_link_title,ad_delivery_start_time,"
    "ad_delivery_stop_time,ad_snapshot_url,page_id,page_name,funding_entity"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s") #configures global logging format


class MetaAdsScraper: # Main scraper encapsultes all scraping behavior so the logic is reusable 
    def __init__(self, token: str, retries: int = 4, base_sleep: float = 1.0):
        self.token = token
        self.retries = retries
        self.base_sleep = base_sleep

    def _backoff(self, attempt: int):
        wait = min(30, self.base_sleep * (2 ** attempt)) + random.uniform(0, 0.5)
        time.sleep(wait) #computes exponential backoff with random jitter

    def _get(self, params: Dict) -> Optional[Dict]:
        for attempt in range(self.retries):
            try: #attempt requests multiple times
                r = requests.get(API_BASE, params=params, timeout=15) #performs HTTP get
                if r.status_code == 429: #detect rate-limiting and respect Retry-after.
                    retry_after = r.headers.get("Retry-After")
                    wait = int(retry_after) if retry_after and retry_after.isdigit() else self.base_sleep * (2 ** attempt)
                    logging.warning("429 received, sleeping %.1fs", wait)
                    time.sleep(wait)
                    continue
                if r.status_code >= 400:
                    try:
                        logging.error("API error %s: %s", r.status_code, r.json())
                    except Exception:
                        logging.error("API error %s: %s", r.status_code, r.text)
                    if 400 <= r.status_code < 500:
        
                        if attempt >= 1:
                            return None
                    self._backoff(attempt)
                    continue
                return r.json()
            except requests.RequestException as e:
                logging.warning("Request exception: %s", e)
                self._backoff(attempt)
        logging.error("All retries failed")
        return None

    def _countries_param(self, countries: List[str]) -> str:
        return json.dumps(countries) #returns JSON array strign

    def search(self,
               term: str,
               search_type: str = "keyword",
               countries: Optional[List[str]] = None,
               limit: int = 100) -> List[Dict]:
        countries = countries or DEFAULT_COUNTRIES
        params = {
            "access_token": self.token,
            "ad_reached_countries": self._countries_param(countries),
            "fields": FIELDS,
            "limit": limit
        }
        if search_type == "keyword":
            params["search_terms"] = term
        elif search_type in ("page_url", "page_slug", "page_id"):
        
            params["search_page_ids"] = term
        else:
            raise ValueError("search_type must be 'keyword', 'page_url', or 'page_slug'")

        ads: List[Dict] = []
        while True:
            logging.info("Requesting ads (total so far: %d)", len(ads))
            data = self._get(params)
            if not data:
                break
            if isinstance(data, dict) and data.get("error"):
                logging.error("API returned error object: %s", data["error"])
                break
            batch = data.get("data", [])
            ads.extend(batch)
            paging = data.get("paging", {})
            cursors = paging.get("cursors", {})
            after = cursors.get("after")
            if not after:
                break

            params = {
                "access_token": self.token,
                "ad_reached_countries": self._countries_param(countries),
                "fields": FIELDS,
                "limit": limit,
                "after": after
            }
            if search_type == "keyword":
                params["search_terms"] = term
            else:
                params["search_page_ids"] = term
        logging.info("Finished. Total ads fetched: %d", len(ads))
        return ads

    @staticmethod  #converts function to be static method
    def export_json(ads: List[Dict], path: str): #write ads list to a JSON file with pretty formating
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ads, f, ensure_ascii=False, indent=2)
        logging.info("Exported %d ads to %s", len(ads), path)

    @staticmethod
    def export_csv(ads: List[Dict], path: str):
        if not ads:
            logging.info("No ads to write to CSV")
            return

        keys = sorted({k for a in ads for k in a.keys()})
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for a in ads:
                writer.writerow({k: a.get(k, "") for k in keys})
        logging.info("Exported %d ads to %s", len(ads), path)



def extract_slug_from_edge(tabs: List[Dict]) -> Optional[str]: #helper
    for t in tabs:
        if t.get("isCurrent"):
            url = t.get("pageUrl", "")
            if url.startswith("<WebsiteContent_") and ">" in url: #remove wrapper marker used in provided metadata format
                try:
                    url = url.split(">", 1)[1].rsplit("<", 1)[0]
                except Exception:
                    pass
            if url:
                parts = url.rstrip("/").split("/")
                return parts[-1] if parts else None
    return None



if __name__ == "__main__":
    scraper = MetaAdsScraper(ACCESS_TOKEN) #we instantiate the scrapper with embedded token.

    slug = extract_slug_from_edge(edge_all_open_tabs)

    ads = scraper.search("climate change", search_type="keyword", countries=["KE"])
    scraper.export_json(ads, "ads.json")
    scraper.export_csv(ads, "ads.csv")






