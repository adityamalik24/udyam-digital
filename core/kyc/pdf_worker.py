"""Draws PDF pages in a process of its own, so a malformed file can only take this process down, not the app.
Reads PDF bytes on stdin and writes each page as a length-prefixed PNG. Exit 3 means too many pages."""
import io, resource, struct, sys

MEMORY_LIMIT = 1024 ** 3
MAX_SIDE = 4000


def main(dpi: int, max_pages: int) -> int:
    try:
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
    except (ValueError, OSError):
        pass  # not enforceable here: the parent's time limit still applies
    import pypdfium2
    pdf = pypdfium2.PdfDocument(sys.stdin.buffer.read())
    if len(pdf) > max_pages: return 3
    for page in pdf:
        buf = io.BytesIO()
        page.render(scale=min(dpi / 72, MAX_SIDE / max(page.get_size()))).to_pil().convert("RGB").save(buf, "PNG")
        sys.stdout.buffer.write(struct.pack(">I", buf.tell()) + buf.getvalue())
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]), int(sys.argv[2])))
