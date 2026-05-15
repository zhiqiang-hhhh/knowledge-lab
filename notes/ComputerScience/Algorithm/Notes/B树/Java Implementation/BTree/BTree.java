package BTree

import java.io.*;
import java.util.List;

public class BTree {
    private static String dataPath = "E:\\Coding\\data";
    private static int minDegree = 2000;
    private static File dir;
    private static TreeNode root;
    private Buffer buffer;

    public BTree(){
        this.buffer = new Buffer(dataPath, minDegree);
        root = new TreeNode(minDegree, buffer);
        //buffer.putTreeNode(root);
        dir = new File(dataPath);

        if (!dir.exists()){
            System.out.println("Create Directory");
            dir.mkdirs();
        }
    }

    private void splitChild(TreeNode s, int index){
        TreeNode z = new TreeNode(minDegree, buffer);
        TreeNode y = buffer.read(s.getChild(index));
        z.setLeaf(y.isLeaf());
        // y is a full child of s, so y.size of childArray is 2t, y.size of keyArray is 2t-1
        // move y's last t-1 key to a new node z
        for(int j = 0; j <= minDegree - 2; j++){
            long k = y.getKey(minDegree);
            z.insertKeyLast(k);
            z.insertMsgList(y.getMessage(k));
            y.removeKey(minDegree);
        }
        // move y's last t children to new node z
        if (!y.isLeaf()){
            for(int j = 0; j <= minDegree - 1; j++){
                z.insertChildLast(y.getChild(minDegree));
                y.removeChild(minDegree);
            }

        }
        // insert z to s.chileArray
        s.insertChild(index + 1, z.getNodeName());
        // move up y's middle key to s
        long t = y.getKey(minDegree-1);
        s.insertKey(index, t);
        s.insertMsgList(y.getMessage(t));
        y.removeKey(minDegree-1);
        buffer.putTreeNode(y);
        buffer.putTreeNode(z);
        buffer.putTreeNode(s);
    }

    public void insertKey(Message msg){
        System.out.println("insertKey:"+msg.getT());
        //System.out.println("freeMemory: "+(Runtime.getRuntime().freeMemory()>>20));
        TreeNode r = BTree.root;
        if(r.isFull()){
            TreeNode s = new TreeNode(minDegree, buffer);
            s.insertChild(0, BTree.root.getNodeName());
            BTree.root = s;
            s.setLeaf(false);
            splitChild(BTree.root, 0);
            insertKeyNotFull(BTree.root, msg);
        }
        else
            insertKeyNotFull(r, msg);
    }

    private void insertKeyNotFull(TreeNode x, Message msg){
        int i = x.getSize() - 1;
        long t = msg.getT();
        if(x.isLeaf()){
            while(i >= 0 && t <= x.getKey(i)){
                i = i - 1;
            }
            x.insertKey(i+1, t);
            x.insertMessage(msg);
            buffer.putTreeNode(x);
            return;
        }
        else while(i>=0 && t <= x.getKey(i)){
            i = i - 1;
        }
        i = i + 1;
        TreeNode xchild = buffer.read(x.getChild(i));
        if(xchild.isFull()){
            splitChild(x, i);
            if(t > x.getKey(i))
                i = i + 1;
            xchild = buffer.read(x.getChild(i));
        }
        insertKeyNotFull(xchild, msg);
    }

    public List<Message> search(long aMin, long aMax, long tMin, long tMax){
        return TreeNode.search(buffer, root, aMin, aMax, tMin, tMax);
    }

}

