
import java.util.*;

public class TreeNode implements java.io.Serializable {
    private static long nodeCount = 0;

    private static List<Message> searchNode(Buffer buffer, TreeNode r, long aMin, long aMax, long t){
        List<Message> res = new ArrayList<>();
        int j = 0;
        while(j < r.keyArray.size() && t > r.keyArray.get(j)){
            j += 1;
        }
        if(j==r.keyArray.size()){//indicates that i is i greater than all keys in keyArray
            if(r.isLeaf())
                return res;
            TreeNode c = buffer.read(r.getChild(j));
            res.addAll(searchNode(buffer, c, aMin, aMax, t));
        }
        else{
            if(t==r.keyArray.get(j)) {
                List<Message> temp = r.getMessage(t);
                for(Message m : temp){
                    if(m.getA() >= aMin && m.getA() <= aMax)
                        res.add(m);
                }
                return res;
            }
            else{
                if(r.isLeaf())
                    return res;
                TreeNode c = buffer.read(r.getChild(j));
                res.addAll(searchNode(buffer, c, aMin, aMax, t));
            }
        }
        return res;

    }
    public static List<Message> search(Buffer buffer, TreeNode r, long aMin, long aMax, long tMin, long tMax){
        List<Message> res = new ArrayList<>();
        for(long i=tMin; i<=tMax; i++){
            res.addAll(searchNode(buffer, r, aMin, aMax, i));
        }
        return res;
    }

    private boolean leaf = true;
    private long minDegree;
    private String name ;

    private LinkedList<Long> keyArray;
    private LinkedList<String> childArray;
    private NavigableMap<Long, List<Message>> msgMap;

    // A new TreeNode, whose minDegree is mD, is put into buffer
    public TreeNode(long mD, Buffer buffer){
        nodeCount += 1;
        this.minDegree = mD;
        this.msgMap = new TreeMap<Long, List<Message>>();
        this.childArray = new LinkedList<>();
        this.keyArray = new LinkedList<>();
        this.name = String.valueOf(nodeCount);
        //new TreeNode is put into buffer immediately
        buffer.putTreeNode(this);
    }

    public TreeNode(long mD, int size){
        nodeCount += 1;
        this.minDegree = mD;
        this.msgMap = new TreeMap<Long, List<Message>>();
        this.childArray = new LinkedList<String>();
        this.keyArray = new LinkedList<>();
        this.name = String.valueOf(nodeCount);
    }

    public boolean isFull(){
        return (this.keyArray.size() >= (2 * minDegree - 1));
    }

    public boolean isLeaf() {
        return this.leaf;
    }

    public String getNodeName(){
        return this.name;
    }

    public int getSize(){
        return this.keyArray.size();
    }

    public long getKey(int index){
        return  this.keyArray.get(index);
    }

    public List<Message> getMessage(long t){
        return msgMap.get(t);
    }

    public LinkedList<String> getChildArray(){
        return this.childArray;
    }
    public LinkedList<Long> getKeyArray(){
        return this.keyArray;
    }

    public String getChild(int index){
        return childArray.get(index);
    }

    public void setLeaf(boolean j){
        this.leaf = j;
    }

    public void insertMsgList(List<Message> mlist){
        long t = mlist.get(0).getT();
        if(msgMap.containsKey(t)){
            msgMap.get(t).addAll(mlist);
        }
        else{
            msgMap.put(t, mlist);
        }
    }

    public void insertMessage(Message msg){
        long t = msg.getT();
        if(msgMap.containsKey(t))
            msgMap.get(t).add(msg);
        else{
            List<Message> nL = new ArrayList<>();
            nL.add(msg);
            msgMap.put(t, nL);
        }
    }

    public void insertKey(int index, long t){
        if(!this.keyArray.contains(t))
            keyArray.add(index, t);
    }
    public void insertKeyLast(long t){
        if(!this.keyArray.contains(t))
            keyArray.addLast(t);
    }

    public void insertChild(int index, String tn){
        this.childArray.add(index, tn);
    }

    public void insertChildLast(String nt){
        this.childArray.addLast(nt);
    }

    public void removeChild(int index){
        if(index < this.childArray.size()){
            this.childArray.remove(index);
        }
    }

    public void removeKey(int index){
        if(index < this.keyArray.size()){
            this.msgMap.remove(this.keyArray.get(index));
            this.keyArray.remove(index);
        }
    }
}