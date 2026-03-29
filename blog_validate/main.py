import typer

app = typer.Typer(help="Validate code blocks in Hugo blog posts.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
