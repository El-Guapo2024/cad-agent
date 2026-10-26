// SPDX-License-Identifier: LGPL-2.1-or-later
//
// A small JSON value, parser and writer for the C API (api.cpp), the same as ui/planegcs/api.cpp's.
#pragma once

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

namespace AsmJson
{

struct Json
{
    enum Kind
    {
        Null,
        Bool,
        Int,
        Float,
        String,
        Array,
        Object
    } kind = Null;
    bool b = false;
    double num = 0;
    long long integer = 0;
    std::string str;
    std::vector<Json> items;
    std::vector<std::string> keys;  // an object's keys, and its values in values
    std::vector<Json> values;

    const Json* get(const char* key) const
    {
        for (size_t k = 0; k < keys.size(); ++k) {
            if (keys[k] == key) {
                return &values[k];
            }
        }
        return nullptr;
    }
    bool isNumber() const
    {
        return kind == Int || kind == Float || kind == Bool;
    }
    double asDouble() const
    {
        if (kind == Int) {
            return double(integer);
        }
        if (kind == Bool) {
            return b ? 1.0 : 0.0;
        }
        if (kind == Float) {
            return num;
        }
        throw std::invalid_argument("expected a number");
    }
    // Python's "i": an int or a bool
    bool isInt() const
    {
        return kind == Int || kind == Bool;
    }
    int asInt() const
    {
        if (kind == Int) {
            return int(integer);
        }
        if (kind == Bool) {
            return b ? 1 : 0;
        }
        throw std::invalid_argument("expected an integer");
    }
};

struct Parser
{
    const char* s;
    size_t i = 0;
    size_t n;

    explicit Parser(const char* text)
        : s(text)
        , n(std::strlen(text))
    {}

    [[noreturn]] void fail(const char* what)
    {
        throw std::invalid_argument(std::string("JSON: ") + what + " at offset " + std::to_string(i));
    }
    void ws()
    {
        while (i < n && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t')) {
            ++i;
        }
    }
    Json parse()
    {
        Json v = value();
        ws();
        if (i != n) {
            fail("trailing characters");
        }
        return v;
    }
    Json value()
    {
        ws();
        if (i >= n) {
            fail("unexpected end");
        }
        char c = s[i];
        Json v;
        if (c == '{') {
            v.kind = Json::Object;
            ++i;
            ws();
            if (i < n && s[i] == '}') {
                ++i;
                return v;
            }
            while (true) {
                ws();
                if (i >= n || s[i] != '"') {
                    fail("expected a key");
                }
                std::string key = string();
                ws();
                if (i >= n || s[i] != ':') {
                    fail("expected ':'");
                }
                ++i;
                v.keys.push_back(key);
                v.values.push_back(value());
                ws();
                if (i < n && s[i] == ',') {
                    ++i;
                    continue;
                }
                if (i < n && s[i] == '}') {
                    ++i;
                    return v;
                }
                fail("expected ',' or '}'");
            }
        }
        if (c == '[') {
            v.kind = Json::Array;
            ++i;
            ws();
            if (i < n && s[i] == ']') {
                ++i;
                return v;
            }
            while (true) {
                v.items.push_back(value());
                ws();
                if (i < n && s[i] == ',') {
                    ++i;
                    continue;
                }
                if (i < n && s[i] == ']') {
                    ++i;
                    return v;
                }
                fail("expected ',' or ']'");
            }
        }
        if (c == '"') {
            v.kind = Json::String;
            v.str = string();
            return v;
        }
        if (std::strncmp(s + i, "true", 4) == 0) {
            i += 4;
            v.kind = Json::Bool;
            v.b = true;
            return v;
        }
        if (std::strncmp(s + i, "false", 5) == 0) {
            i += 5;
            v.kind = Json::Bool;
            return v;
        }
        if (std::strncmp(s + i, "null", 4) == 0) {
            i += 4;
            return v;
        }
        // number
        size_t start = i;
        bool isFloat = false;
        if (s[i] == '-' || s[i] == '+') {
            ++i;
        }
        while (i < n && ((s[i] >= '0' && s[i] <= '9') || s[i] == '.' || s[i] == 'e' || s[i] == 'E'
                         || s[i] == '-' || s[i] == '+')) {
            if (s[i] == '.' || s[i] == 'e' || s[i] == 'E') {
                isFloat = true;
            }
            ++i;
        }
        if (i == start) {
            fail("unexpected character");
        }
        std::string tok(s + start, i - start);
        if (tok == "NaN" || tok == "Infinity") {
            fail("bad number");
        }
        if (isFloat) {
            v.kind = Json::Float;
            v.num = std::strtod(tok.c_str(), nullptr);
        }
        else {
            v.kind = Json::Int;
            v.integer = std::strtoll(tok.c_str(), nullptr, 10);
        }
        return v;
    }
    std::string string()
    {
        std::string out;
        ++i;  // opening quote
        while (i < n && s[i] != '"') {
            if (s[i] == '\\' && i + 1 < n) {
                ++i;
                switch (s[i]) {
                    case 'n':
                        out += '\n';
                        break;
                    case 't':
                        out += '\t';
                        break;
                    case 'r':
                        out += '\r';
                        break;
                    case 'b':
                        out += '\b';
                        break;
                    case 'f':
                        out += '\f';
                        break;
                    case 'u': {
                        if (i + 4 >= n) {
                            fail("bad escape");
                        }
                        unsigned cp = std::strtoul(std::string(s + i + 1, 4).c_str(), nullptr, 16);
                        i += 4;
                        if (cp < 0x80) {
                            out += char(cp);
                        }
                        else if (cp < 0x800) {
                            out += char(0xC0 | (cp >> 6));
                            out += char(0x80 | (cp & 0x3F));
                        }
                        else {
                            out += char(0xE0 | (cp >> 12));
                            out += char(0x80 | ((cp >> 6) & 0x3F));
                            out += char(0x80 | (cp & 0x3F));
                        }
                        break;
                    }
                    default:
                        out += s[i];
                }
                ++i;
            }
            else {
                out += s[i++];
            }
        }
        if (i >= n) {
            fail("unterminated string");
        }
        ++i;  // closing quote
        return out;
    }
};

// JSON writing ---------------------------------------------------------------------------------

struct Writer
{
    std::string out;
    void num(double v)
    {
        if (!std::isfinite(v)) {
            out += "null";
            return;
        }
        char buf[32];
        std::snprintf(buf, sizeof buf, "%.17g", v);
        out += buf;
    }
    void integer(long long v)
    {
        out += std::to_string(v);
    }
    void str(const std::string& v)
    {
        out += '"';
        for (char c : v) {
            if (c == '"' || c == '\\') {
                out += '\\';
                out += c;
            }
            else if (c == '\n') {
                out += "\\n";
            }
            else if (static_cast<unsigned char>(c) < 0x20) {
                char buf[8];
                std::snprintf(buf, sizeof buf, "\\u%04x", c);
                out += buf;
            }
            else {
                out += c;
            }
        }
        out += '"';
    }
    void key(const char* k)
    {
        if (!out.empty() && out.back() != '{' && out.back() != '[') {
            out += ',';
        }
        str(k);
        out += ':';
    }
    void sep()
    {
        if (!out.empty() && out.back() != '{' && out.back() != '[') {
            out += ',';
        }
    }
    void ints(const std::vector<int>& v)
    {
        out += '[';
        for (size_t k = 0; k < v.size(); ++k) {
            if (k) {
                out += ',';
            }
            integer(v[k]);
        }
        out += ']';
    }
};

}  // namespace AsmJson
