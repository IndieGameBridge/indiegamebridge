"""The request parser the whole API shares."""

from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser


class JsonObjectParser(JSONParser):
    """JSON with an object at the top, the only shape this API takes.

    Views read the body as a dict, so a body like `["search"]` would be a 500 in
    the first line that does. That line isn't always in the view: a throttle can
    read the body before it.
    """

    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type, parser_context)
        if not isinstance(data, dict):
            raise ParseError("Expected a JSON object.")
        return data
