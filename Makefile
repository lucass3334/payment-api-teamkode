run:
    poetry run uvicorn app.main:app --reload

test:
    poetry run pytest tests/

lint:
    poetry run flake8 app/

format:
    poetry run black app/ tests/

install:
    poetry install
