from rise.console import configure_console_stream


class FakeStream:
    def __init__(self):
        self.options = None

    def reconfigure(self, **options):
        self.options = options


def test_console_stream_replaces_unencodable_output():
    stream = FakeStream()

    configure_console_stream(stream)

    assert stream.options == {"errors": "backslashreplace"}
