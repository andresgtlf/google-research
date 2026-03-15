# 1. Extract information and generate the research prompt
uv run python main.py

# 2. Perform the deep research (replace 'NewProject' with your actual filename)
uv run python research.py json/NewProject.json

# 3. Export the results to Markdown and PDF
uv run python export.py research_results/NewProject_research.json