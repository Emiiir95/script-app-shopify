"""
Tests unitaires — features/reviews/generator.py

Couvre : generate_global_note, generate_reviews_for_product
"""
import json
import unittest
from unittest.mock import MagicMock

from features.reviews.generator import generate_global_note, generate_reviews_for_product
from utils.cost_tracker import CostTracker


def _make_openai_response(avis_list, prompt_tokens=100, completion_tokens=200):
    """Helper : crée un mock de réponse OpenAI."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps({"avis": avis_list})
    mock_response.usage.prompt_tokens    = prompt_tokens
    mock_response.usage.completion_tokens = completion_tokens
    return mock_response


SAMPLE_AVIS = [
    {"note": "5.0", "titre": "Super",   "texte": "Très bien",  "nom_auteur": "Jean D."},
    {"note": "4.8", "titre": "Bien",    "texte": "Content",    "nom_auteur": "Marie L."},
    {"note": "4.9", "titre": "Top",     "texte": "Excellent",  "nom_auteur": "Paul B."},
]


class TestGenerateGlobalNote(unittest.TestCase):
    def test_returns_three_element_tuple(self):
        result = generate_global_note()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_rating_between_4_3_and_5_0(self):
        for _ in range(30):
            _, rating, _ = generate_global_note()
            self.assertGreaterEqual(rating, 4.3)
            self.assertLessEqual(rating, 5.0)

    def test_count_between_150_and_500(self):
        for _ in range(30):
            _, _, count = generate_global_note()
            self.assertGreaterEqual(count, 150)
            self.assertLessEqual(count, 500)

    def test_string_contains_rating_and_count(self):
        note_str, rating, count = generate_global_note()
        self.assertIn(str(rating), note_str)
        self.assertIn(str(count), note_str)

    def test_string_is_html_formatted(self):
        note_str, _, _ = generate_global_note()
        self.assertIn("<strong>", note_str)
        self.assertIn("avis vérifiés", note_str)


class TestGenerateReviewsForProduct(unittest.TestCase):
    def test_returns_correct_number_of_reviews(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(SAMPLE_AVIS)

        result = generate_reviews_for_product("Veilleuse", 3, mock_client, "system prompt", CostTracker())
        self.assertEqual(len(result), 3)

    def test_duplicates_reviews_when_api_returns_fewer_than_requested(self):
        one_avis = [{"note": "5.0", "titre": "Super", "texte": "Bien", "nom_auteur": "Jean D."}]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(one_avis)

        result = generate_reviews_for_product("Veilleuse", 4, mock_client, "system prompt", CostTracker())
        self.assertEqual(len(result), 4)

    def test_truncates_reviews_when_api_returns_more_than_requested(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(SAMPLE_AVIS)

        result = generate_reviews_for_product("Veilleuse", 2, mock_client, "system prompt", CostTracker())
        self.assertEqual(len(result), 2)

    def test_cost_tracker_is_updated_after_call(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(
            SAMPLE_AVIS[:1], prompt_tokens=500, completion_tokens=300
        )
        tracker = CostTracker()
        generate_reviews_for_product("Produit", 1, mock_client, "system prompt", tracker)

        self.assertEqual(tracker.calls, 1)
        self.assertEqual(tracker.total_input_tokens, 500)
        self.assertEqual(tracker.total_output_tokens, 300)

    def test_raises_after_max_retries_on_non_quota_error(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Internal server error")

        with self.assertRaises(Exception) as ctx:
            generate_reviews_for_product("Produit", 1, mock_client, "system", CostTracker(), max_retries=2)
        self.assertIn("Échec génération", str(ctx.exception))

    def test_uses_product_title_in_prompt(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(SAMPLE_AVIS[:1])

        generate_reviews_for_product("Veilleuse Magique XL", 1, mock_client, "system", CostTracker())

        call_messages = mock_client.chat.completions.create.call_args[1]["messages"]
        user_message = next(m for m in call_messages if m["role"] == "user")
        self.assertIn("Veilleuse Magique XL", user_message["content"])

    def test_uses_gpt4o_mini_model(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response(SAMPLE_AVIS[:1])

        generate_reviews_for_product("Produit", 1, mock_client, "system", CostTracker())

        model_used = mock_client.chat.completions.create.call_args[1]["model"]
        self.assertEqual(model_used, "gpt-4o-mini")


if __name__ == "__main__":
    unittest.main()
