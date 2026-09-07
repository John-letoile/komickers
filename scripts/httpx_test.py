from pathlib import Path

import httpx

url = "https://getcomics.org/dls/UuuIGuKucVJGvf2IzVkqKspX3tjmGQIloubBAVJ4xeLwVFbFU4Li5Ue6/wrjz64qbGu3LgAisEv6RZuGcYxZ/WoGf+ohOzN74mo/933SGWIYV41fnJokJzKGZuTgLuzzJxPMrVqvGNkgG56HC824N1o7j3daNeMsr2IOc/Zqei8oltVNQ+dtbkWgEqsYVlL7:MWqnGoh+7d65hkpryw8E+g=="

path = Path("test.txt")
with httpx.Client() as client:
    try:
        response: httpx.Response = client.head(
            "https://getcomics.org/marvel/captain-america-4-2027/",
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        print("HI")
