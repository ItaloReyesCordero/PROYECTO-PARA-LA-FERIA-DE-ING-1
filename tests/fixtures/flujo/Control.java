public class Control {
    int precio(String tipo) {
        int r = switch (tipo) {
            case "a" -> 1;
            default -> 2;
        };
        switch (tipo) {
            case "x" -> System.out.println("equis");
            case "y" -> {
                System.out.println("ye");
                r++;
            }
            default -> throw new IllegalStateException("tipo");
        }
        for (String s : new String[] {"a", "b"}) {
            try {
                r += s.length();
            } catch (RuntimeException e) {
                break;
            } finally {
                r--;
            }
        }
        return r;
    }
}
