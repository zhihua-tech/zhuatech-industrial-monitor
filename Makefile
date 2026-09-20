.PHONY: test check run
test:
	python3 -m unittest discover -s tests -v
check:
	python3 -m compileall -q app tests
run:
	python3 -m app.server
