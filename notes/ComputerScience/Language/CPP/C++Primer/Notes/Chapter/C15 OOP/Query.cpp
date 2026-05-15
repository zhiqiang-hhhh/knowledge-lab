#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>

using namespace std;

class QueryResult;
class TextQuery {
 public:
  using line_no = std::vector<std::string>::size_type;
  TextQuery(std::ifstream&);
  QueryResult query(const std::string&) const;

 private:
  std::shared_ptr<std::vector<std::string>> file;
  std::map<std::string, std::shared_ptr<std::set<line_no>>> wm;
};

TextQuery::TextQuery(std::ifstream& is) : file(new std::vector<std::string>) {
  std::string text;
  while (getline(is, text)) {
    file->push_back(text);
    int n = file->size - 1;
    std::istringstream line(text);
    std::string word;
    while (line >> word) {
      auto& lines = wm[word];
      if (!lines) {
        lines.reset(new set<line_no>);
      }
      lines->insert(n);
    }
  }
}

class QueryResult {
  friend std::ostream& print(std::ostream&, const QueryResult&);

 public:
  QueryResult(std::string s, std::shared_ptr<std::set<line_no>> p,
              std::shared_ptr<std::vector<std::string>> f)
      : sought(s), lines(p), file(f) {}

 private:
  std::string sought;
  std::shared_ptr<std::set<line_no>> lines;
  std::shared_ptr<std::vector<std::string>> file;
};

QueryResult TextQuery::query(const std::string& sought) const {
  static std::shared_ptr<set<line_no>> nodata(new set<line_no>);
  auto loc = wm.find(sought);
  if (loc == wm.end())
    return QueryResult(sought, nodata, file);
  else
    return QueryResult(sought, loc->second, file);
}

string make_plural(size_t ctr, const std::string& word, const string& ending) {
  return (ctr > 1) ? word + ending : word;
}

ostream& print(ostream& os, const QueryResult& qr) {
  os << qr.sought << " occurs " << qr.lines->size() << " "
     << make_plural(qr.lines->size(), "times", "s") << endl;
  for (auto num : *qr.lines)
    os << "\t(line " << num + 1 << ") " << *(qr.file->begin() + num) << endl;
  return os;
}

class Query_base {
  friend class Query;

 protected:
  using line_no = TextQuery::line_no;
  virtual ~Query_base() = default;

 private:
  // eval 返回满足本次查询的 QueryResult
  virtual Query_Result eval(const TestQuery&) const = 0;
  // rep 是本次查询的 string 形式
  virtual std::string rep() const = 0;
};

class Query {
  friend Query operator~(const Query&);
  friend Query operator|(const Query&, const Query&);
  friend Query operator&(const Query&, const Query&);

 public:
  Query(const std::string&);
  Query_Result eval(const TextQuery& t) const { return q->eval(t); }
  std::string rep() const { return q->rep(); }

 private:
  Query(std::shared_ptr<Query_base> query) : q(query) {}
  std::shared_ptr<Query_base> q;
};

// Query andq = Query(sought1) & Query(sought2)
// std::cout << andq << std::endl;
std::ostream& operator<<(std::ostream& os, cosnt Query& query) {
  return os << query.rep();
}

class WordQuery : public Query_base {
  friend class Query;
  WordQuery(cosnt std::string& s) : query_word(s) {}
  QueryResult eval(const TextQuery& t) const { return t.query(query_word); }
  std::string rep() const { return qurey_word; }
  std::string query_word;
};

Query::Query(const std::string& s) : q(new WordQuery(s)) {}

class NotQuery : public Query_Base {
  friend Query operator~(const Query&);
  NotQuery(const Query& q) : query(q) {}
  std::string rep() const { return "~(" + query.rep() + ")"; }
  QueryResult eval(const TextQuery&) const;
  Query query;
};

inline Query operator~(const Query& operand) {
  // 分配一个新的 NotQuery 对象
  // 将指向该对象的指针绑定到一个 shared_ptr<Query_base>
  return std::shared_ptr<Query_base>(new NotQuery(operand));
}

class BinaryQuery : public Query_base {
 protected:
  BinaryQuery(const Query& l, const Query& r, std::string s)
      : lhs(l), rhs(r), opSym(s) {}
  std::string rep() const {
    return "(" + lhs.rep() + " " + opSym + " " + rhs.rep() + ")";
  }
  Query lhs, rhs;
  std::string opSym;
};

class AndQuery : public BinaryQuery {
  friend Query operator&(const Query&, const Query&);
  AndQuery(const Query& left, const Query& right)
      : BinaryQuery(left, right, "&") {}
  QueryResult eval()(const TextQuery&) const;
};
inline Query operator&(const Query& lhs, const Query& rhs) {
  return std::shared_ptr<Query_base>(new AndQuery(lhs, rhs));
}

QueryResult AndQuery::eval(const TextQuery& text) const {
  auto left = lhs.eval(text), right = rhs.eval(text);
  auto ret_lines = make_shared<set<line_no>>();
  set_intersection(left.begin(), left.end(), right.begin(), right.end(),
                   inserter(*ret_lines, ret_lines->begin()));
  return QueryResult(rep(), ret_lines, left.get_file());
}
