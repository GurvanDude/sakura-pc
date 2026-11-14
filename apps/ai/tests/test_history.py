"""Tests de l'historique local."""

import json

import pytest

from sakura_ai.history import ChatHistory, ChatStore


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


def test_store_cree_ecrit_et_trie_sans_enregistrer_le_vide(sakura_home, monkeypatch):
    store = ChatStore()
    empty = store.create()
    assert not (sakura_home / "ai" / "chats").exists()

    moments = iter([
        "2026-11-14T10:00:00+00:00",
        "2026-11-14T10:30:00+00:00",
        "2026-11-14T11:00:00+00:00",
    ])
    monkeypatch.setattr("sakura_ai.history._now", lambda: next(moments))
    store.append(empty["id"], "user", "Première question")
    second = store.create()
    store.append(second["id"], "user", "Deuxième question")

    assert [item["id"] for item in store.list()] == [second["id"], empty["id"]]
    assert store.load(empty["id"])["messages"][0]["content"] == "Première question"


def test_migration_de_lancien_chat(sakura_home):
    legacy = sakura_home / "ai" / "chat.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps([{"role": "user", "content": "Comment ranger mes fichiers ?"}]), encoding="utf-8")

    store = ChatStore()

    assert store.list()[0]["title"] == "Comment ranger mes fichiers ?"
    assert not legacy.exists()
    assert legacy.with_name("chat.migrated.json").exists()


def test_suppression_deplace_dans_la_corbeille(sakura_home):
    store = ChatStore()
    chat = store.create()
    store.append(chat["id"], "user", "À garder")

    store.delete(chat["id"])

    assert store.list() == []
    assert (sakura_home / "ai" / "chats" / ".trash" / f"{chat['id']}.json").exists()


@pytest.mark.parametrize("chat_id", ["../x", "..\\x", "C:\\secret", "", "a" * 33])
def test_identifiants_invalides_refuses(sakura_home, chat_id):
    store = ChatStore()
    with pytest.raises(ValueError):
        store.load(chat_id)


def test_titre_automatique_necrase_pas_un_titre_renomme(sakura_home):
    store = ChatStore()
    chat = store.create()
    store.append(chat["id"], "user", "Question initiale")
    store.rename(chat["id"], "Mon titre à moi")

    store.rename(chat["id"], "Titre automatique", automatic=True)

    assert store.load(chat["id"])["title"] == "Mon titre à moi"

