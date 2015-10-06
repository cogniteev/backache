import unittest

from backache.utils import nameddict


class TestNamedDict(unittest.TestCase):
    def test_from_empty_dict(self):
        n = nameddict({})
        self.assertTrue(len(n) == 0)
        self.assertEqual(len(n), 0)
        n['foo'] = 42  # dict syntax
        self.assertEqual(len(n), 1)
        self.assertEqual(n.foo, 42)
        self.assertEqual(n['foo'], 42)
        self.assertEqual(n.keys(), ['foo'])
        n.bar = 43  # obj syntax
        self.assertEqual(len(n), 2)
        self.assertEqual(n.bar, 43)
        self.assertEqual(n['bar'], 43)
        self.assertItemsEqual(n.keys(), ['foo', 'bar'])

    def test_dict_assignment(self):
        n = nameddict()
        n.foo = {
            'bar': 42,
            'pika': {
                'plop': 43
            },
        }
        self.assertEqual(n.foo.bar, 42)
        self.assertEqual(n.foo.pika.plop, 43)
        n['bar'] = {
            'bar': 44,
            'pika': {
                'plop': 45
            },
        }
        self.assertEqual(n.bar.bar, 44)
        self.assertEqual(n.bar.pika.plop, 45)


if __name__ == '__main__':
    unittest.main()
