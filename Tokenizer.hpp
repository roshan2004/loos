/*
  KernelValue.hpp
  (c) 2008 Tod D. Romo


  Grossfield Lab
  Department of Biochemistry and Biophysics
  University of Rochester Medical School

*/


#if !defined(TOKENIZER_HPP)
#define TOKENIZER_HPP



#include <iostream>
#include <string>
#include <stdexcept>
#include <deque>

#include <string.h>


using namespace std;


namespace loos {


  struct Token {
    enum TokenType { NONE, ID, NUMERIC, STRING, OPERATOR, PARENS };

    TokenType type;
    string datum;

    Token() : type(NONE), datum("NONE") { }


    void setId(const string s) { datum = s; type = ID; }
    void setNumeric(const string s) { datum = s; type = NUMERIC; }
    void setString(const string s) { datum = s; type = STRING; }
    void setOperator(const string s) { datum = s; type = OPERATOR; }
    void setParens(const string s) { datum = s; type = PARENS; }

    friend ostream& operator<<(ostream& os, const Token& t) {
      os << "<TOKEN TYPE='";
      switch(t.type) {
      case ID: os << "ID"; break;
      case NUMERIC: os << "NUMERIC" ; break;
      case STRING: os << "STRING" ; break;
      case OPERATOR: os << "OPERATOR" ; break;
      case PARENS: os << "PARENS"; break;
      default: throw(logic_error("Should never be here"));
      }

      os << "'>" << t.datum << "</TOKEN>";

      return(os);
    }


  };


  typedef deque<Token> Tokens;


  class Tokenizer {
    Tokens _tokens;
    Tokens _undo;

    string text;

  public:
    Tokenizer(const string s) : text(s) { tokenize(); }
    Tokenizer() { }

    void tokenize(void);
    void tokenize(const string s) { _tokens.clear(); text = s; tokenize(); }

    Tokens& tokens(void) { return(_tokens); }


    // Note: we're popping/pushing to the front in this case...
    Token pop(void) {
      if (_tokens.empty()) {
	Token t;
	return(t);
      }

      Token t = _tokens.front();
      _tokens.pop_front();
      _undo.push_back(t);
      return(t);
    }

    void push(const Token& t) {
      _tokens.push_front(t);
    }

    void restore(void) {
      Tokens::iterator i;
      for (i = _undo.end(); i >= _undo.begin(); i--)
	_tokens.push_front(*i);
      _undo.clear();
    }

    void clearUndo(void) {
      _undo.clear();
    }

    friend ostream& operator<<(ostream& os, const Tokenizer& t) {
      Tokens::const_iterator i;

      for (i=t._tokens.begin(); i != t._tokens.end(); i++) 
	os << *i << endl;

      return(os);
    }
  };


};



#endif
