#include <set>
#include <string>
#include <vector>

class Folder;

class Message {
  friend class Folder;

 public:
  explicit Message(const std::string& str = "") : contents(str) {}
  Message(const Message&);
  Message& operator=(const Message&);
  ~Message();

  void save(Folder&);
  void remove(Folder&);

 private:
  std::string contents;
  std::set<Folder*> folders;
  void add_to_Folders(const Message&);
  void remove_from_Folders();
};

void Message::save(Folder& f) {
  folders.insert(&f);
  f.addMsg(this);
}

void Message::remove(Folder& f) {
  folders.erase(&f);
  f.remMsg(this);
}

// 把 this Message 添加到所有包含 m 的 Folder 中
void Message::add_to_Folders(const Message& m) {
  for (auto f : m.folders) {
    f->addMsg(this);
  }
}

Message::Message(const Message& m) : contents(m.contents), folders(m.folders) {
  add_to_Folders(m);
}

void Message::remove_from_Folders() {
  for (auto f : folders) {
    f->remMsg(this);
  }
}

Message::~Message() { remove_from_Folders(); }

Message& Message::operator=(const Message& rhs) {
  remove_from_Folders();
  contents = rhs.contents;
  folders = rhs.folders;
  add_to_Folders();
  return *this;
}

void swap(Message* lhs， Message& rhs) {
  using std::swap;

  for (auto f : lhs.folders) {
    f->remMsg(&lsh);
  }
  for (auto f : rhs.folders) {
    f->remMsg(&rhs);
  }

  swap(lhs.folders, rhs.folders);
  swap(lhs.contents, rhs.contents);

  for (auto f : lhs.folders) {
    f->addMsg(&lhs);
  }

  for (auto f : rhs.folders) {
    f->addMsg(&rhs);
  }
}

class Folder {
  friend class Message;

 public:
  Folder() : msgs() {}
  Folder(class Folder&);
  void addMsg(class Message*);
  void remMsg(class Message*);
  ~Folder();

 private:
  std::set<Message*> msgs;
};

void Folder::addMsg(class Message* msg) {
  msgs.insert(msg);
  // msg->save(this);
}

void Folder::remMsg(class Message* msg) {
  msgs.erase(msg);
  //
}

Folder::Folder(class Folder& folder) : msgs(folder.msgs) {
  for (auto m : msgs) {
    m->save(*this);
  }
}