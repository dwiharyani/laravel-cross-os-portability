from datetime import datetime
import csv
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv() 

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


url = "https://api.github.com/search/repositories"

headers = {
     "Authorization": f"Bearer {GITHUB_TOKEN}"
}

max_pages = 10
all_projects = []

def fetch_projects(order, pushed_after="2025-01-01"):

    stars_threshold = 1
    flag = True
    while flag:

        for page in range(1, max_pages + 1):
            params = {
                "q": f"topic:laravel language:php stars:>{stars_threshold} pushed:>{pushed_after}",
                "sort": "stars",
                "order": order,
                "per_page": 100,
                "page": page,
            }

            response = requests.get(url, params=params, headers=headers)

            if response.status_code != 200:
                print(f"Error on page {page}: {response.status_code}")
                print(response.json())
                flag = False
                break

            items = response.json().get("items", [])
            if not items:
                flag = False
                break

            if page == 10:
                if items[-1]["stargazers_count"] == stars_threshold:
                    stars_threshold += 1
                else:
                    stars_threshold = items[-1]["stargazers_count"]
            
            all_projects.extend(items)
            print(f"Fetched page {page} ({len(items)} items) with stars threshold {stars_threshold}")

            time.sleep(1)




fetch_projects("asc")


all_projects = sorted(all_projects, key=lambda x: x["stargazers_count"], reverse=True)


timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
filename = f"laravel_projects_{timestamp}.csv"

with open(filename, "w", newline="", encoding="utf-8") as csvfile:
    
    writer = csv.writer(csvfile)
    writer.writerow(["name", "url", "stars", "description"])
    for repo in all_projects:
        writer.writerow(
            [
                repo["full_name"],
                repo["html_url"],
                repo["stargazers_count"],
                repo["description"],
            ]
        )

print(f"Done! Total saved: {len(all_projects)}")