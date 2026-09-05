from app.files import safe_filename


def test_safe_filename_strips_directories():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("C:\\\\Windows\\\\photo.jpg") == "photo.jpg"


def test_safe_filename_rejects_hidden_and_empty():
    assert safe_filename("..") == "evidence.bin"
    assert safe_filename("") == "evidence.bin"
    assert not safe_filename(".env").startswith(".")


def test_safe_filename_caps_length():
    name = safe_filename("a" * 300 + ".jpg")
    assert len(name) <= 128
    assert name.endswith(".jpg")
