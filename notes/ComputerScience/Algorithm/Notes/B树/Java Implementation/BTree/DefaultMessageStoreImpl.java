import java.io.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 这是一个简单的基于内存的实现，以方便选手理解题意；
 * 实际提交时，请维持包名和类名不变，把方法实现修改为自己的内容；
 */
public class DefaultMessageStoreImpl extends MessageStore {
    private BTree root;
    public DefaultMessageStoreImpl(){
        this.root = new BTree();
    }


    @Override
    public synchronized void put(Message message) {
        root.insertKey(message);
    }

    @Override
    public synchronized List<Message> getMessage(long aMin, long aMax, long tMin, long tMax) {
        //List<Message> res = new LinkedList<>();
        return root.search(aMin,aMax,tMin,tMax);

        //return res;
    }

    @Override
    public long getAvgValue(long aMin, long aMax, long tMin, long tMax) {
        long sum = 0;
        long count = 0;
        return count;
    }

}