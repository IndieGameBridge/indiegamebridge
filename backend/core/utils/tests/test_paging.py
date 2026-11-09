"""A page number is kept within the pages a list has."""

from django.test import SimpleTestCase

from core.utils.paging import page_of


class PageOfTests(SimpleTestCase):
    def test_counts_the_pages(self):
        self.assertEqual(page_of("2", 101, 50), (2, 3))
        self.assertEqual(page_of("2", 100, 50), (2, 2))

    def test_no_rows_make_one_empty_page(self):
        self.assertEqual(page_of(None, 0, 50), (1, 1))

    def test_a_page_past_the_end_reads_as_the_last(self):
        for raw in ("3", "99999999999999999999999"):
            with self.subTest(raw=raw):
                self.assertEqual(page_of(raw, 51, 50), (2, 2))

    def test_anything_else_reads_as_the_first(self):
        for raw in (None, "", "abc", "2.5", "0", "-5"):
            with self.subTest(raw=raw):
                self.assertEqual(page_of(raw, 120, 50), (1, 3))
