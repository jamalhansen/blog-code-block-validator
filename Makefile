include $(HOME)/projects/py-tooling/Makefile.common

validate-newsletter:
	uv run blog-validate check --all -v --config configs/newsletter.toml
