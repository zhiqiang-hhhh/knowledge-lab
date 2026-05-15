import java.io.*;
import java.util.LinkedList;
import java.util.List;


public class Main {

    public static void main(String[] args) throws Exception{
        /*
        DefaultMessageStoreImpl store = new DefaultMessageStoreImpl();
        //BTree root = new BTree();
        byte b[] = {123};
        for(int i = 0; i < 55; i++){
            Message msg = new Message(i*100, i, b);
            store.put(msg);
        }

        List<Message> res =  store.getMessage(0, 5000, 0, 56);

        for(Message i: res){
            System.out.println(i.getA());
        }

         */

        //TreeNode tmp = BTree.Read("2");
        //System.out.println(tmp.getKeyArray());
        long m = Runtime.getRuntime().totalMemory()/1024/1024;
        System.out.println(m);

        System.out.println(Runtime.getRuntime().maxMemory());
        System.out.println(Runtime.getRuntime().freeMemory());

        DemoTester.main();
    }
        /*
        File dir = new File(dataPath);
        if(!dir.exists()){
            dir.mkdirs();
        }

        Node n = new Node();
        n.setName("1");
        //System.out.println("Hello World!");
        File file = new File(dir, n.getName());
        if(file.exists())
             System.out.println("File Exists");
        else
            try{
                file.createNewFile();
            }
            catch(IOException ioe){
                System.out.println("Create File ERROE");
            }

        try{
            ObjectOutputStream outputStream =
                    new ObjectOutputStream(new FileOutputStream(file));
            outputStream.writeObject(n);
            outputStream.close();
        }
        catch (IOException ioe){
            System.out.println("Open file ERROR");
        }

        try{
            ObjectInputStream inputStream =
                    new ObjectInputStream(new FileInputStream(file));
            Node nn = (Node)inputStream.readObject();
            System.out.println("Node name is: " + nn.getName());
        }
        catch (ClassNotFoundException nfe){
            ;
        }

         */
}
