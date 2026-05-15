# Copy Control
类通过 copy constructor, move constructor, copy-assignmrnt operator, move-assignment operator and destructor 来控制当对象发生 copy, assign, move 或者 destroy 行为时应当做什么。

A constructor is the copy constructor if its first parameter is a reference to the class
type and any additional parameters have default values.

当我们没有为某个类定义 copy constructor 时，编译器会生成一个合成的 copy constructor。

拷贝初始化：通过另一个类对象拷贝构造一个类对象的行为。
**拷贝初始化发生的时机：**
1. Pass an object as an arugment to a parameter of **nonreference type**.
2. Return an object from a function that has a nonreference return type.
3. Brace initialize the element in an array or the members of an aggregate class.

The library containers copy initialize their elements when we initialize the container, or
when we call an insert or push member. By contrast, elements created by an emplace member are direct initialized.