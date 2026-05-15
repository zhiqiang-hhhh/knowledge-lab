#include<string>
#include<set>
#include<iostream>

class Message{
    friend class Folder;
    friend void swap(Message &, Message &);

public:
    explicit Message(const std::string &str = " "):
        contents(str) {}
    Message(const Message &m) : 
        contents(m.contents), folders(m.folders) { add_to_Folders(m); }

    Message &operator=(const Message &);

    void save(Folder &);
    void remove(Folder &);
    void addFldr(Folder *);

    ~Message();
private:
    std::string contents;
    std::set<Folder *> folders;

    void add_to_Folders(const Message &);
    void remove_from_Folders();
};

void swap(Message &lhs, Message &rhs)
{
    using std::swap;
    for(auto f : lhs.folders)
        f->remMsg(&lhs);
    for(auto f : rhs.folders)
        f->remMsg(&rhs);

    swap(lhs.contents, rhs.contents);
    swap(lhs.folders, rhs.folders);

    for(auto f : lhs.folders)
        f->addMsg(&lhs);
    for(auto f : rhs.folders)
        f->addMsg(&rhs);
}

Message& Message::operator=(const Message &msg)
{
    remove_from_Folders();
    contents = msg.contents;
    folders = msg.folders;
    return *this;
}

void Message::save(Folder &f)
{
    folders.insert(&f);
    f.addMsg(this);
}
void Message::remove(Folder &f)
{
    folders.erase(&f);
    f.remMsg(this);
}

Message::~Message()
{
    remove_from_Folders();
}

void Message::add_to_Folders(const Message &msg)
{
    for(auto f : msg.folders)
        f->addMsg(this);
}

void Message::remove_from_Folders()
{
    for(auto f : folders)
        f->remMsg(this);
}

class Folder{
    friend class Message;
public:
    Folder();
    Folder(const Folder &f):
        Msg(f.Msg) 
        {
            for(auto msg: f.Msg)
                msg->folders.insert(this);
        }
    void remMsg(Message *);
    void addMsg(Message *);
private:
    std::set<Message *> Msg;
    void add_to_Message(const Folder &);
};

void Folder::remMsg(Message *msg)
{
    Msg.erase(msg);
}

void Folder::addMsg(Message* msg)
{
    Msg.insert(msg);
}

void Folder::add_to_Message(const Folder &f)
{
    for(auto msg : f.Msg)
        msg->save(*this);
}