reformat:
	poetry run isort .
	poetry run black .

run:
	poetry run uvicorn --app-dir evse main:evse --reload
