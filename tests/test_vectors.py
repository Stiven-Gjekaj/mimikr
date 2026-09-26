from mimikr.vectors import cosine


def test_the_cosine_of_a_zero_vector_is_zero():
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0
