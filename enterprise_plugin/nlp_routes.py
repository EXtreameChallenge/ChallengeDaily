"""P321-P330: NLP路由"""
from flask import Blueprint, request, jsonify
from nlp_engine import (
    Tokenizer, POSTagger, NERecognizer, SentimentAnalyzer,
    _keyword_extractor, Summarizer, TextClassifier, LanguageDetector,
    SpellChecker, _similarity,
)

bp = Blueprint("nlp", __name__, url_prefix="/api/nlp")


@bp.route("/tokenize", methods=["POST"])
def nlp_tokenize():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    method = data.get("method", "default")
    if method == "bigram":
        tokens = Tokenizer.tokenize_bigram(text)
    else:
        tokens = Tokenizer.tokenize(text)
    return jsonify({"tokens": tokens, "count": len(tokens)})


@bp.route("/pos", methods=["POST"])
def nlp_pos():
    data = request.get_json(silent=True) or {}
    tokens = data.get("tokens", [])
    if not tokens:
        tokens = Tokenizer.tokenize(data.get("text", ""))
    return jsonify({"tags": POSTagger.tag(tokens)})


@bp.route("/ner", methods=["POST"])
def nlp_ner():
    data = request.get_json(silent=True) or {}
    return jsonify({"entities": NERecognizer.recognize(data.get("text", ""))})


@bp.route("/sentiment", methods=["POST"])
def nlp_sentiment():
    data = request.get_json(silent=True) or {}
    return jsonify(SentimentAnalyzer.analyze(data.get("text", "")))


@bp.route("/keywords", methods=["POST"])
def nlp_keywords():
    data = request.get_json(silent=True) or {}
    top_k = data.get("top_k", 10)
    return jsonify({"keywords": _keyword_extractor.extract(data.get("text", ""), top_k)})


@bp.route("/keywords/add-doc", methods=["POST"])
def nlp_keywords_add():
    data = request.get_json(silent=True) or {}
    _keyword_extractor.add_document(data.get("doc_id", ""), data.get("text", ""))
    return jsonify({"status": "ok"})


@bp.route("/summarize", methods=["POST"])
def nlp_summarize():
    data = request.get_json(silent=True) or {}
    max_s = data.get("max_sentences", 3)
    return jsonify(Summarizer.summarize(data.get("text", ""), max_s))


_classifier = TextClassifier()


@bp.route("/classify/train", methods=["POST"])
def nlp_classify_train():
    data = request.get_json(silent=True) or {}
    _classifier.train(data.get("text", ""), data.get("category", ""))
    return jsonify({"status": "ok"})


@bp.route("/classify", methods=["POST"])
def nlp_classify():
    data = request.get_json(silent=True) or {}
    return jsonify(_classifier.classify(data.get("text", "")))


@bp.route("/detect-language", methods=["POST"])
def nlp_detect():
    data = request.get_json(silent=True) or {}
    return jsonify(LanguageDetector.detect(data.get("text", "")))


@bp.route("/spell-check", methods=["POST"])
def nlp_spell():
    data = request.get_json(silent=True) or {}
    return jsonify(SpellChecker.check(data.get("word", "")))


@bp.route("/similarity", methods=["POST"])
def nlp_similar():
    data = request.get_json(silent=True) or {}
    t1 = data.get("text1", "")
    t2 = data.get("text2", "")
    method = data.get("method", "cosine")
    if method == "jaccard":
        score = _similarity.jaccard_similarity(t1, t2)
    elif method == "levenshtein":
        score = _similarity.levenshtein_ratio(t1, t2)
    else:
        score = _similarity.cosine_similarity(t1, t2)
    return jsonify({"score": round(score, 4), "method": method})
