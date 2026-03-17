"""
Tests unitaires — features/reviews/prompts.py

Couvre : build_system_prompt, build_user_prompt
"""
import unittest

from features.reviews.prompts import build_system_prompt, build_user_prompt


FULL_MD = {
    "marketing.md": "Veilleuse multicolore USB-C avec télécommande",
    "persona1.md":  "Parent 28-40 ans avec jeunes enfants",
    "persona2.md":  "Personne âgée qui cherche un éclairage doux",
    "persona3.md":  "Acheteur cadeau pour anniversaire",
}


class TestBuildSystemPrompt(unittest.TestCase):
    def test_contains_marketing_content(self):
        prompt = build_system_prompt(FULL_MD)
        self.assertIn("Veilleuse multicolore USB-C", prompt)

    def test_contains_all_three_personas(self):
        prompt = build_system_prompt(FULL_MD)
        self.assertIn("Parent 28-40 ans", prompt)
        self.assertIn("Personne âgée", prompt)
        self.assertIn("Acheteur cadeau", prompt)

    def test_contains_language_rule(self):
        prompt = build_system_prompt(FULL_MD)
        self.assertIn("français", prompt)

    def test_contains_note_range_constraint(self):
        prompt = build_system_prompt(FULL_MD)
        self.assertIn("4.5", prompt)
        self.assertIn("5.0", prompt)

    def test_contains_json_output_constraint(self):
        prompt = build_system_prompt(FULL_MD)
        self.assertIn("JSON", prompt)

    def test_handles_empty_md_contents(self):
        prompt = build_system_prompt({})
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 50)  # Les règles sont toujours présentes

    def test_handles_partial_md_contents(self):
        partial = {"marketing.md": "Contenu marketing seulement"}
        prompt = build_system_prompt(partial)
        self.assertIn("Contenu marketing seulement", prompt)
        self.assertIsInstance(prompt, str)

    def test_returns_string(self):
        prompt = build_system_prompt(FULL_MD)
        self.assertIsInstance(prompt, str)


class TestBuildUserPrompt(unittest.TestCase):
    def test_contains_product_title(self):
        prompt = build_user_prompt("Veilleuse Magique Pro", 3)
        self.assertIn("Veilleuse Magique Pro", prompt)

    def test_contains_review_count(self):
        prompt = build_user_prompt("Produit Test", 5)
        self.assertIn("5", prompt)

    def test_different_counts_appear_in_prompt(self):
        for n in [1, 3, 8]:
            prompt = build_user_prompt("Produit", n)
            self.assertIn(str(n), prompt)

    def test_contains_json_schema_keys(self):
        prompt = build_user_prompt("Produit Test", 2)
        self.assertIn("avis", prompt)
        self.assertIn("note", prompt)
        self.assertIn("titre", prompt)
        self.assertIn("texte", prompt)
        self.assertIn("nom_auteur", prompt)

    def test_returns_string(self):
        prompt = build_user_prompt("Produit", 3)
        self.assertIsInstance(prompt, str)

    def test_handles_special_characters_in_title(self):
        prompt = build_user_prompt('Veilleuse "Étoile" & Lune', 2)
        self.assertIn("Veilleuse", prompt)


if __name__ == "__main__":
    unittest.main()
