include $(HOME)/projects/py-tooling/Makefile.common

# The three real targets this tool validates. The blog carries its own
# blog-validate.toml (and the pre-commit hook); the vault and the newsletter
# patterns are validated through the configs in configs/.
validate-blog:
	cd $(HOME)/projects/jamalhansen.com && uv run --project $(CURDIR) blog-validate check --all

validate-vault:
	uv run blog-validate check --all --config configs/vault.toml

validate-newsletter:
	uv run blog-validate check --all -v --config configs/newsletter.toml

validate-all: validate-blog validate-vault validate-newsletter
