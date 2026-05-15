/*  允许用户在一个给定的文件中查询单词
    查询结果是单词的出现次数和其所在行的列表
*/
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using namespace std;

class TextQuery;
class QueryResult;

void print(ostream&, const QueryResult&);

class TextQuery {
 public:
  using line_no = vector<string>::size_type;
  TextQuery(istream&);
  QueryResult query(const string& targ) const;

 private:
  shared_ptr<vector<string>> text_sp;
  shared_ptr<map<string, shared_ptr<set<line_no>>>> strMap_sp;
};

TextQuery::TextQuery(istream& in)
    : text_sp(make_shared<vector<string>>()),
      strMap_sp(make_shared<map<string, shared_ptr<set<line_no>>>>()) {
  string buff;
  line_no n = 0;  // 行号

  //  从 istream 中读取一行保存到 string 中
  while (getline(in, buff)) {
    ++n;
    //  将 string 对象转换为字节流 istringstream
    istringstream m_line(buff);
    string word;
    //  从字节流 istringstream 中读取一个单词到 string 中
    while (m_line >> word) {
      //  lines 保存从 map 中查找 word 后得到的 shared_ptr<set<line_no>>
      auto& lines = (*strMap_sp)[word];
      //  如果 lines 为空，说明该 word 第一次出现
      //  动态创建一个 set 用来为该 word 保存行号
      if (!lines) lines.reset(new set<line_no>);
      //  在该 word 对应的 set 中添加行号
      lines->insert(n);
    }
    //  将文本行保存到 vector<string> 中
    text_sp->push_back(buff);
  }
}

class QueryResult {
  friend void print(ostream&, const QueryResult&);

 public:
  QueryResult(string s, shared_ptr<set<TextQuery::line_no>> _line_sp,
              shared_ptr<vector<string>> _text_sp)
      : targ(s), line_sp(_line_sp), text_sp(_text_sp) {}

 private:
  string targ;
  shared_ptr<set<TextQuery::line_no>> line_sp;
  shared_ptr<vector<string>> text_sp;
};

QueryResult TextQuery::query(const string& targ) const {
  static shared_ptr<set<TextQuery::line_no>> nodata(new set<line_no>);
  auto loc = strMap_sp->find(targ);

  if (loc == strMap_sp->end()) return QueryResult(targ, nodata, text_sp);
  return QueryResult(targ, loc->second, text_sp);
}

void print(ostream& out, const QueryResult& qr) {
  out << qr.targ << " occurs " << qr.line_sp->size() << " times " << endl;
}
void runQuerry(ifstream& ifile) {
  TextQuery tq(ifile);
  string targ;

  while (true) {
    ::cout << "Enter word to look for, or q to exit\n";
    if (!(cin >> targ) || targ == "q") break;
    print(cout, tq.query(targ));
  }
}

int main() {
  ifstream infile("动态内存.md");
  runQuerry(infile);
}