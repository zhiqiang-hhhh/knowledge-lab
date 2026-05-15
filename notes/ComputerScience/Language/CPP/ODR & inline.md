* Wikipedia:

Translation unit: Ultimate input to a C or C++ compiler from which an object file is generated. 即编译预处理之后得到的文件。A translation unit roughly consists of a source file after it has been processed by the C preprocessor.

One Definition Rule(ODR): Classes/structs and **non-inline** functions cannot have more than one definition in the entire program and template and types cannot have more than one definition by translation unit.

In short:
1. In any translation unit, a template, type, funtion or object can have no more than one definition.
2. In the entire program, an object or **non-inline** function cannot have more than one definition; if an object or function is used, it must have exactly one definition.
3. Some things, like types, templates and extern inline functions, can be defined in more than one translation unit. For a given entity, each definition must have the same sequence tokens. Non-extern objects and functions in different translation units are different entities, even if their names and types are the same.

Some violations of the ODR must be diagnosed by the compiler. Other violations, particularly those that span translation units, are not required to be diagnosed.

* cppreference

One and only one definition of **every non-inline** function or variable that is odr-used (see below) is required to appear in the entire program (including any standard and user-defined libraries). The compiler is not required to diagnose this violation, but the behavior of the program that violates it is undefined.

For an **inline function or inline variable (since C++17)**, a definition is required in every translation unit where it is odr-used.

There can be more than one definition in a program of each of the following: class type, enumeration type, **inline function**, inline variable (since C++17), templated entity (template or member of template, but not full template specialization), as long as all of the following is true:
* each definition appears in a different translation unit (出现在不同的TU中)
* each definition consists of the same sequence of tokens (typically, appears in the same header file)
* ...

If all these requirements are satisfied, the program behaves as if there is only one definition in the entire program. Otherwise, the program is ill-formed, no diagnostic required.



不论函数是否为内联，在任何的TU内部，都不允许出现重复定义。