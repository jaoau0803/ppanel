import unittest

from release import metadata


class ReleaseMetadataTest(unittest.TestCase):
    def test_dispatch(self):
        for version in ('1.2.3', 'v1.2.3', 'node-v1.2.3'):
            self.assertEqual(metadata('workflow_dispatch', 'branch', 'main', version), ('node-v1.2.3', False))

    def test_tag(self):
        self.assertEqual(metadata('push', 'tag', 'node-v1.2.3-rc.1', ''), ('node-v1.2.3-rc.1', True))
        self.assertEqual(metadata('workflow_dispatch', 'tag', 'node-v1.2.3', '1.2.3'), ('node-v1.2.3', False))

    def test_invalid(self):
        for value in ('', '01.2.3', '1.2', '1.2.3\nBAD=1', '1.2.3-rc.01', 'backend-v1.2.3'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                metadata('workflow_dispatch', 'branch', 'main', value)
        with self.assertRaises(ValueError):
            metadata('workflow_dispatch', 'tag', 'node-v1.2.3', '1.2.4')


if __name__ == '__main__':
    unittest.main()
