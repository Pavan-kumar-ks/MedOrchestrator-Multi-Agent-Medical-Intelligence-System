url = "https://atlas.mappls.com/api/places/nearby/json"

headers = {
    "Authorization": f"Bearer {"pduvmchpvzekkxmjtzlolgqxkoxqzonqwizn"}"
}

params = {
    "keywords": "hospital",
    "refLocation": "12.9716,77.5946",
    "radius": 5000
}

res = requests.get(url, headers=headers, params=params)

print(res.status_code)
print(res.json())