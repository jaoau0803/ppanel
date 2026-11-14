import unittest
from metadata import metadata


class MetadataTests(unittest.TestCase):
    def env(self, **overrides):
        return {"RELEASE_VERSION": "1.2.3", "GITHUB_REPOSITORY_OWNER": "Example", "BACKEND_SHA": "a" * 40, **overrides}

    def test_stable_defaults(self):
        result = metadata(self.env())
        self.assertEqual(result["image"], "ghcr.io/example/ppanel-backend")
        self.assertEqual(result["channel"], "stable")
        self.assertNotIn(":latest", result["tags"])
        self.assertIn("1.2.3-sha-aaaaaaaaaaaa", result["tags"])

    def test_latest_is_explicit(self):
        self.assertIn(":latest", metadata(self.env(PUBLISH_LATEST="true"))["tags"])

    def test_parent_tag_selects_version(self):
        result = metadata(self.env(GITHUB_REF="refs/tags/backend-v2.0.0-rc.1"))
        self.assertEqual(result["version"], "2.0.0-rc.1")
        self.assertEqual(result["channel"], "beta")

    def test_invalid_versions_and_latest(self):
        for version in ["", "1.2", "01.2.3", "1.2.3;echo injected", "1.2.3\nother=value", "1.2.3-beta.01"]:
            with self.subTest(version=version), self.assertRaises(ValueError):
                metadata(self.env(RELEASE_VERSION=version))
        with self.assertRaises(ValueError):
            metadata(self.env(RELEASE_VERSION="1.2.3-beta.1", PUBLISH_LATEST="true"))


if __name__ == "__main__":
    unittest.main()
