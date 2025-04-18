import requests

# python3 tests/stream_test.py

# Replace with your actual endpoint URL and query parameters
url_1 = "http://localhost:5000/request_podcast?url=https://dcs-spotify.megaphone.fm/NPR3009618033.mp3?e%3D1237991513%26key%3D8c9a2f4ca4acbfdc0db9196ec77c9f9a%26p%3D510318%26request_event_id%3D740d3051-abc4-4572-a064-d8ef745708c3%26size%3D12973916%26t%3Dpodcast%26timetoken%3D1742488288_C281F9873B3D18CA327CAE1FF0CBB0F2 "
response = requests.get(url_1)
print(response)

url_2 = "http://localhost:5000/stream_podcast?url=https://dcs-spotify.megaphone.fm/NPR3009618033.mp3?e%3D1237991513%26key%3D8c9a2f4ca4acbfdc0db9196ec77c9f9a%26p%3D510318%26request_event_id%3D740d3051-abc4-4572-a064-d8ef745708c3%26size%3D12973916%26t%3Dpodcast%26timetoken%3D1742488288_C281F9873B3D18CA327CAE1FF0CBB0F2 "

response = requests.get(url_2, stream=True)

for chunk in response.iter_content(chunk_size=4870000):
    if chunk:
        print("Received chunk")
