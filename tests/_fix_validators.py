import sys

filepath = "/home/sanju/WORK/DATA-ENGINEER-LEARNING-JOURNEY/02-projects/etl-projects/03-job-data-pipeline/tests/test_silver_validators.py"

with open(filepath, 'rb') as f:
    content = f.read()

old = (
    b'    @pytest.fixture\r\n'
    b'    def valid_dataframe(self):\r\n'
    b'        """Fixture for valid dataframe."""\r\n'
    b'        return pd.DataFrame(\r\n'
    b'            {\r\n'
    b'                "job_id": ["id1","id2","id3"],\r\n'
    b'                "job_title": ["Data Engineer","Backend Dev","Frontend Dev"],\r\n'
    b'                "company_name": ["Company A","Company B","Company C"],\r\n'
    b'                "location": ["Jakarta","Bandung","Surabaya"],\r\n'
    b'                "job_url": [\r\n'
    b'                    "http://example.com/1",\r\n'
    b'                    "http://example.com/2",\r\n'
    b'                    "http://example.com/3",\r\n'
    b'                ],\r\n'
    b'                "platform": ["kalibrr","glints","jobstreet"],\r\n'
    b'                "scraped_at": ["20260305_090000"] * 3,\r\n'
    b'                "keyword": ["data-engineer"] * 3,\r\n'
    b'            }\r\n'
    b'        )\r\n'
    b'\r\n'
    b'    def test_validate_valid_dataframe(self, valid_dataframe):\r\n'
    b'        """Test validation passes for valid dataframe."""\r\n'
    b'        result = validate_silver_schema(valid_dataframe)\r\n'
    b'        assert len(result) == 3\r\n'
    b'        assert list(result.columns) == [\r\n'
    b'            "job_id",\r\n'
    b'            "job_title",\r\n'
    b'            "company_name",\r\n'
    b'            "location",\r\n'
    b'            "job_url",\r\n'
    b'            "platform",\r\n'
    b'            "scraped_at",\r\n'
    b'            "keyword",\r\n'
    b'        ]'
)

print("Old pattern length:", len(old))
print("File content length:", len(content))

idx = content.find(old)
if idx >= 0:
    print("Pattern found at position:", idx)
else:
    print("Pattern NOT found")
    # Check if it's a whitespace issue - search for a substring
    partial = b'"job_id": ["id1","id2","id3"]'
    idx2 = content.find(partial)
    if idx2 >= 0:
        print(f"Found partial match at {idx2}")
        print(f"Context: {content[idx2-50:idx2+len(partial)+50]}")
