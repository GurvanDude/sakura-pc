"""Tests de l'historique local."""

from sakura_ai.history import ChatHistory


def test_historique_aller_retour(sakura_home):
    history = ChatHistory()
    history.append("user", "Bonjour Sakura")
    history.append("assistant", "Coucou Gurvan")

    restored = ChatHistory()
    assert restored.messages == [
        {"role": "user", "content": "Bonjour Sakura"},
        {"role": "assistant", "content": "Coucou Gurvan"},
    ]
    assert not list((sakura_home / "ai").glob("*.tmp"))


def test_historique_corrompu_repart_de_zero(sakura_home):
    file = sakura_home / "ai" / "chat.json"
    file.parent.mkdir(parents=True)
    file.write_text("{cassé", encoding="utf-8")

    history = ChatHistory()
    assert history.messages == []
    history.append("user", "Nouveau départ")
    assert ChatHistory().messages == [{"role": "user", "content": "Nouveau départ"}]


def test_nouvelle_discussion_vide_le_fichier(sakura_home):
    history = ChatHistory()
    history.append("user", "À effacer")
    history.clear()
    assert ChatHistory().messages == []

