# Common
### COW
**TL;DR**
COW(Copy On Write) 是一个模版类，实例化该类后，继承类将拥有一系列方法用以实现COW特性。
`COW::Ptr` 是一个 refCounted smart pointer to immutable object T。由于 immutable，因此 `COW::Ptr`可以 copy construct/move construct/copy assignment，多个 `COW::Ptr` 指向同一个 immutable object。

`COW::MutablePtr` 则对应 smart pointer to mutable object T。由于对象是 mutable，因此`COW::MutablePtr`禁止 copy construct/copy assignment，但是允许 move construct。


```cpp
template<typename Derived>
class COW : public boost::intrusive_ref_counter<Derived>
{
private:
    /// A. 根据 this 的 const 属性，返回调用合适的 derived 函数。
    Derived * derived() { return static_cast<Derived *>(this); }
    const Derived * derived() const { return static_cast<const Derived *>(this); }
protected:
    /// B. mutable_ptr，禁止copy construct，但是是可以move construct
    template <typename T>
    class mutable_ptr : public boost::intrusive_ptr<T> /// NOLINT
    {
    private:
        using Base = boost::intrusive_ptr<T>;

        template <typename> friend class COW;
        template <typename, typename> friend class COWHelper;

        explicit mutable_ptr(T * ptr) : Base(ptr) {}

    public:
        /// Copy: not possible.
        mutable_ptr(const mutable_ptr &) = delete;

        /// Move: ok.
        mutable_ptr(mutable_ptr &&) = default; /// NOLINT
        mutable_ptr & operator=(mutable_ptr &&) = default; /// NOLINT

        /// Initializing from temporary of compatible type.
        template <typename U>
        mutable_ptr(mutable_ptr<U> && other) : Base(std::move(other)) {} /// NOLINT

        mutable_ptr() = default;

        mutable_ptr(std::nullptr_t) {} /// NOLINT
    };
public:
    using MutablePtr = mutable_ptr<Derived>;

protected:
    template <typename T>
    class immutable_ptr : public boost::intrusive_ptr<const T> /// NOLINT
    {
    private:
        using Base = boost::intrusive_ptr<const T>;

        template <typename> friend class COW;
        template <typename, typename> friend class COWHelper;

        explicit immutable_ptr(const T * ptr) : Base(ptr) {}

    public:
        /// Copy from immutable ptr: ok.
        immutable_ptr(const immutable_ptr &) = default;
        immutable_ptr & operator=(const immutable_ptr &) = default;

        template <typename U>
        immutable_ptr(const immutable_ptr<U> & other) : Base(other) {} /// NOLINT

        /// Move: ok.
        immutable_ptr(immutable_ptr &&) = default; /// NOLINT
        immutable_ptr & operator=(immutable_ptr &&) = default; /// NOLINT

        /// Initializing from temporary of compatible type.
        template <typename U>
        immutable_ptr(immutable_ptr<U> && other) : Base(std::move(other)) {} /// NOLINT

        /// C. immutable_ptr
        /// Move from mutable ptr: ok.
        template <typename U>
        immutable_ptr(mutable_ptr<U> && other) : Base(std::move(other)) {} /// NOLINT

        /// Copy from mutable ptr: not possible.
        template <typename U>
        immutable_ptr(const mutable_ptr<U> &) = delete;

        immutable_ptr() = default;

        immutable_ptr(std::nullptr_t) {} /// NOLINT
    };

public:
    using Ptr = immutable_ptr<Derived>;

    /// D. create 方法只会返回 MutablePtr,
    template <typename... Args>
    static MutablePtr create(Args &&... args) { return MutablePtr(new Derived(std::forward<Args>(args)...)); }

    template <typename T>
    static MutablePtr create(std::initializer_list<T> && arg) { return create(std::forward<std::initializer_list<T>>(arg)); }

    /// E. const overload
    Ptr getPtr() const { return static_cast<Ptr>(derived()); }
    MutablePtr getPtr() { return static_cast<MutablePtr>(derived()); }

protected:
    /// F. 从一个 immutable ptr 构造一个 mutable ptr 需要保证安全
    MutablePtr shallowMutate() const
    {
        if (this->use_count() > 1)
            return derived()->clone();
        else
            return assumeMutable();
    }

public:
    static MutablePtr mutate(Ptr ptr)
    {
        return ptr->shallowMutate();
    }

    /// G: 直接 const_cast，很危险
    MutablePtr assumeMutable() const
    {
        return const_cast<COW*>(this)->getPtr();
    }

    Derived & assumeMutableRef() const
    {
        return const_cast<Derived &>(*derived());
    }

/// H:TODO: chameleon_ptr
protected:
    /// It works as immutable_ptr if it is const and as mutable_ptr if it is non const.
    template <typename T>
    class chameleon_ptr /// NOLINT
    {
    private:
        immutable_ptr<T> value;

    public:
        template <typename... Args>
        chameleon_ptr(Args &&... args) : value(std::forward<Args>(args)...) {} /// NOLINT

        template <typename U>
        chameleon_ptr(std::initializer_list<U> && arg) : value(std::forward<std::initializer_list<U>>(arg)) {}

        const T * get() const { return value.get(); }
        T * get() { return &value->assumeMutableRef(); }

        const T * operator->() const { return get(); }
        T * operator->() { return get(); }

        const T & operator*() const { return *value; }
        T & operator*() { return value->assumeMutableRef(); }

        operator const immutable_ptr<T> & () const { return value; } /// NOLINT
        operator immutable_ptr<T> & () { return value; } /// NOLINT

        /// Get internal immutable ptr. Does not change internal use counter.
        immutable_ptr<T> detach() && { return std::move(value); }

        explicit operator bool() const { return value != nullptr; }
        bool operator! () const { return value == nullptr; }

        bool operator== (const chameleon_ptr & rhs) const { return value == rhs.value; }
        bool operator!= (const chameleon_ptr & rhs) const { return value != rhs.value; }
    };

public:
    /** Use this type in class members for compositions.
      *
      * NOTE:
      * For classes with WrappedPtr members,
      * you must reimplement 'mutate' method, so it will call 'mutate' of all subobjects (do deep mutate).
      * It will guarantee, that mutable object have all subobjects unshared.
      *
      * NOTE:
      * If you override 'mutate' method in inherited classes, don't forget to make it virtual in base class or to make it call a virtual method.
      * (COW itself doesn't force any methods to be virtual).
      *
      * See example in "cow_compositions.cpp".
      */
    using WrappedPtr = chameleon_ptr<Derived>;
};
```
A: derived 通过 const 实现重载
B: 保证不会有多个 mutable_ptr 指向
C: immutable_ptr 可以通过 std::move(mutable_ptr) 构造，后面会发现如果我们是第一次构造 immutable_ptr，那似乎只能通过这种方式（因为第一次构造该对象！无法拷贝构造/赋值）`IColumn::Ptr ptr(IColumn::create(...));`
D: create 方法只会返回 MutablePtr，通过 Ptr(COW::create(...)) 从一个MutablePtr移动构造一个Ptr
E: 同样的，const 实现重载
F: 如果当前 immutable ptr 的 refcount == 1，则可以安全地将当前指针的 const 属性去掉，直接转换成一个 mutable ptr，否则会进行一次拷贝
G: 直接 const_cast，很危险
H:TODO: chameleon_ptr

### type cast

```cpp
/** Checks type by comparing typeid.
  * The exact match of the type is checked. That is, cast to the ancestor will be unsuccessful.
  * In the rest, behaves like a dynamic_cast.
  */
template <typename To, typename From>
requires std::is_reference_v<To>
To typeid_cast(From & from)
{
    try
    {
        if ((typeid(From) == typeid(To)) || (typeid(from) == typeid(To)))
            return static_cast<To>(from);
    }
    catch (const std::exception & e)
    {
        throw DB::Exception::createDeprecated(e.what(), DB::ErrorCodes::LOGICAL_ERROR);
    }

    throw DB::Exception(DB::ErrorCodes::LOGICAL_ERROR, "Bad cast from type {} to {}",
                        demangle(typeid(from).name()), demangle(typeid(To).name()));
}
```
```cpp
template <typename To, typename From>
requires std::is_pointer_v<To>
To typeid_cast(From * from)
{
    try
    {
        if ((typeid(From) == typeid(std::remove_pointer_t<To>)) || (from && typeid(*from) == typeid(std::remove_pointer_t<To>)))
            return static_cast<To>(from);
        else
            return nullptr;
    }
    catch (const std::exception & e)
    {
        throw DB::Exception::createDeprecated(e.what(), DB::ErrorCodes::LOGICAL_ERROR);
    }
}
```
