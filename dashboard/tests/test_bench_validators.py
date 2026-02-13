import pytest
from benchmarking.validators import (
    validate_flag_name,
    validate_flag_value,
    validate_params,
    validate_service_name,
)


class TestValidateFlagName:
    @pytest.mark.parametrize("flag", ["-p", "-ngl", "-fa", "-b", "--threads", "-C", "--flash-attn"])
    def test_valid_flags(self, flag):
        valid, err = validate_flag_name(flag)
        assert valid is True
        assert err is None

    def test_empty_flag(self):
        valid, err = validate_flag_name("")
        assert valid is False
        assert "empty" in err.lower()

    def test_no_dash_prefix(self):
        valid, err = validate_flag_name("ngl")
        assert valid is False
        assert "start with" in err.lower()

    def test_reserved_flag_m(self):
        valid, err = validate_flag_name("-m")
        assert valid is False
        assert "Reserved" in err

    def test_reserved_flag_o(self):
        valid, err = validate_flag_name("-o")
        assert valid is False
        assert "Reserved" in err

    @pytest.mark.parametrize("flag", ["-;inject", "-$var", "-flag name", "-a&b"])
    def test_invalid_characters(self, flag):
        valid, err = validate_flag_name(flag)
        assert valid is False

    def test_just_dashes(self):
        valid, err = validate_flag_name("--")
        assert valid is False


class TestValidateFlagValue:
    @pytest.mark.parametrize("value", ["512", "128", "99", "", "0.5", "layer", "f16"])
    def test_valid_values(self, value):
        valid, err = validate_flag_value(value)
        assert valid is True

    @pytest.mark.parametrize("value", ["; rm -rf /", "$(evil)", "foo|bar", "a`cmd`b", "line\nbreak"])
    def test_unsafe_values(self, value):
        valid, err = validate_flag_value(value)
        assert valid is False
        assert "unsafe" in err.lower()

    def test_too_long_value(self):
        valid, err = validate_flag_value("x" * 1025)
        assert valid is False
        assert "long" in err.lower()


class TestValidateParams:
    def test_valid_params(self):
        params = {"-p": "512", "-n": "128", "-ngl": "99", "-fa": ""}
        valid, err = validate_params(params)
        assert valid is True

    def test_not_a_dict(self):
        valid, err = validate_params("not a dict")
        assert valid is False

    def test_too_many_params(self):
        params = {f"-flag{i}": str(i) for i in range(51)}
        valid, err = validate_params(params)
        assert valid is False
        assert "Too many" in err

    def test_invalid_flag_in_params(self):
        params = {"-p": "512", "no-dash": "value"}
        valid, err = validate_params(params)
        assert valid is False

    def test_reserved_flag_in_params(self):
        params = {"-m": "/some/path"}
        valid, err = validate_params(params)
        assert valid is False
        assert "Reserved" in err

    def test_non_string_value(self):
        params = {"-p": 512}
        valid, err = validate_params(params)
        assert valid is False
        assert "string" in err.lower()

    def test_empty_params(self):
        valid, err = validate_params({})
        assert valid is True


class TestValidateServiceName:
    @pytest.mark.parametrize("name", ["llamacpp-test", "my_service", "svc1"])
    def test_valid_names(self, name):
        valid, err = validate_service_name(name)
        assert valid is True

    def test_empty_name(self):
        valid, err = validate_service_name("")
        assert valid is False

    def test_none_name(self):
        valid, err = validate_service_name(None)
        assert valid is False

    def test_too_long(self):
        valid, err = validate_service_name("a" * 101)
        assert valid is False

    def test_special_characters(self):
        valid, err = validate_service_name("svc;drop table")
        assert valid is False
