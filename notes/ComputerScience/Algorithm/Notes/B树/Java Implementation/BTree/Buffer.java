import java.io.*;
import java.util.Iterator;
import java.util.LinkedList;
import java.util.TreeMap;

public class Buffer {
    private static long maxSize = 100;
    private static File dir;

    //node name to treenode
    private TreeMap<String, TreeNode> store = new TreeMap<>();
    private int minDegree;

    public Buffer(String dataPath, int m){
        dir = new File(dataPath);

        if(!dir.exists()){
            dir.mkdirs();
        }

        this.minDegree = m;
    }

    private boolean isFull(){
        return store.size() >= maxSize;
    }

    public void putTreeNode(TreeNode treeNode){
        //if treeNode is contained in store, then replace the older with the new
        if (store.containsKey(treeNode.getNodeName())){
            store.replace(treeNode.getNodeName(), treeNode);
        }
        else{
            if(this.isFull()){
                LinkedList<TreeNode> lru = LRU();
                for(TreeNode i: lru)
                    diskWrite(i);
                this.store.put(treeNode.getNodeName(), treeNode);
            }
            else
                this.store.put(treeNode.getNodeName(), treeNode);
        }
    }

    private LinkedList<TreeNode> LRU(){
        LinkedList<TreeNode> res = new LinkedList<>();
        for(int i=0; i<maxSize/2;i++) {
            String longest = this.store.firstKey();
            res.add(this.store.get(longest));
            store.remove(longest);
        }
        return res;
        /*
        LinkedList<TreeNode> res = new LinkedList<>();
        store.firstEntry().getKey();
        int i = 0;
        while(i<maxSize/2){
            String longest = store.firstEntry().getKey();
            res.add(this.store.get(longest));
            store.remove(longest);
            i += 1;
        }
        return res;
         */
    }

    private void diskWrite(TreeNode treeNode){
        File file = new File(dir, treeNode.getNodeName());
        if (!file.exists()){
            try{
                //System.out.println("Create New File");
                file.createNewFile();
            }
            catch (IOException ioe){
                System.out.println("Create File ERROR");
            }
        }

        try {
            ObjectOutputStream output =
                    new ObjectOutputStream(new FileOutputStream(file));
            output.writeObject(treeNode);
            System.out.println("writeObject: " + treeNode.getNodeName());
            treeNode = null;
            output.close();
        }
        catch (IOException ioe){
            System.out.println("Object Output Error");
        }
    }

    public TreeNode read(String nodeName){
        if (store.containsKey(nodeName)){
            return store.get(nodeName);
        }
        else{
            TreeNode res = diskRead(nodeName);

            if(this.isFull()){
                LinkedList<TreeNode> lru = LRU();
                for(TreeNode i : lru)
                    this.diskWrite(i);
                store.put(nodeName, res);
            }
            return res;
        }
    }

    private TreeNode diskRead(String name){

        File file = new File(dir, name);
        TreeNode res = new TreeNode(minDegree, this);
        try{
            ObjectInputStream input =
                    new ObjectInputStream(new FileInputStream(file));
            res = (TreeNode)input.readObject();
            input.close();
        }
        catch (IOException ioe){
            System.out.println("Object Input Error");
        }
        catch (ClassNotFoundException nf){
            System.out.println("ClassNotFoundException");
        }
        return res;
    }
}

