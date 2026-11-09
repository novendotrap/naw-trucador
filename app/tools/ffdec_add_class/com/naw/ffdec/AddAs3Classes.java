package com.naw.ffdec;

import com.jpexs.decompiler.flash.SWF;
import com.jpexs.decompiler.flash.abc.ABC;
import com.jpexs.decompiler.flash.abc.ScriptPack;
import com.jpexs.decompiler.flash.abc.avm2.parser.script.ActionScript3Parser;
import com.jpexs.decompiler.flash.abc.avm2.parser.script.AbcIndexing;
import com.jpexs.decompiler.flash.tags.ABCContainerTag;
import com.jpexs.decompiler.flash.tags.DoABC2Tag;
import com.jpexs.decompiler.flash.tags.Tag;
import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;

/**
 * CLI helper mirroring FFDec GUI "Add class":
 * creates missing AS3 classes in an existing DoABC via ActionScript3Parser.addScript,
 * then they can be replaced/filled with full source.
 *
 * Usage:
 *   java -cp ... com.naw.ffdec.AddAs3Classes <infile.swf> <outfile.swf> <ClassName>[=<source.as>] [...]
 */
public class AddAs3Classes {
    public static void main(String[] args) throws Exception {
        if (args.length < 3) {
            System.err.println("Usage: AddAs3Classes <infile.swf> <outfile.swf> <ClassName>[=source.as] [...]");
            System.exit(2);
        }
        File inFile = new File(args[0]);
        File outFile = new File(args[1]);
        if (!inFile.isFile()) {
            System.err.println("Missing infile: " + inFile);
            System.exit(1);
        }

        SWF swf;
        try (FileInputStream fis = new FileInputStream(inFile);
             BufferedInputStream bis = new BufferedInputStream(fis)) {
            swf = new SWF(bis, true);
        }

        ABCContainerTag container = null;
        for (Tag t : swf.getTags()) {
            if (t instanceof ABCContainerTag) {
                container = (ABCContainerTag) t;
                break;
            }
        }
        if (container == null) {
            DoABC2Tag doAbc2 = new DoABC2Tag(swf);
            swf.addTag(doAbc2);
            doAbc2.setTimelined(swf);
            container = doAbc2;
        }

        ABC abc = container.getABC();
        AbcIndexing abcIndex = swf.getAbcIndex();
        abcIndex.selectAbc(abc);

        List<ABC> allAbcs = new ArrayList<>();
        for (ABCContainerTag ct : swf.getAbcList()) {
            allAbcs.add(ct.getABC());
        }

        int added = 0;
        int skipped = 0;
        ActionScript3Parser parser = new ActionScript3Parser(abcIndex);

        for (int i = 2; i < args.length; i++) {
            String spec = args[i];
            String className;
            String sourcePath = null;
            int eq = spec.indexOf('=');
            if (eq > 0) {
                className = spec.substring(0, eq).trim();
                sourcePath = spec.substring(eq + 1).trim();
            } else {
                className = spec.trim();
            }
            if (className.isEmpty()) {
                continue;
            }

            ScriptPack existing = abc.findScriptPackByPath(className, allAbcs);
            if (existing != null) {
                System.out.println("SKIP exists: " + className);
                skipped++;
                continue;
            }

            String script;
            if (sourcePath != null && !sourcePath.isEmpty()) {
                script = new String(Files.readAllBytes(new File(sourcePath).toPath()), StandardCharsets.UTF_8);
                // Ensure package wrapper if donor export already has it — leave as-is.
            } else {
                String pkg = className.contains(".") ? className.substring(0, className.lastIndexOf('.')) : "";
                String simple = className.contains(".")
                        ? className.substring(className.lastIndexOf('.') + 1)
                        : className;
                script = "package " + pkg + " {\n"
                        + "public class " + simple + " {\n"
                        + "}\n"
                        + "}\n";
            }

            String fileName = className.replace('.', '/');
            System.out.println("ADD " + className + (sourcePath != null ? " from " + sourcePath : " (empty)"));
            parser.addScript(script, fileName, 0, 0, swf.getDocumentClass(), abc);
            ((Tag) container).setModified(true);
            added++;
        }

        swf.clearAllCache();
        swf.setModified(true);
        try (FileOutputStream fos = new FileOutputStream(outFile)) {
            swf.saveTo(fos);
        }
        System.out.println("OK added=" + added + " skipped=" + skipped + " -> " + outFile.getAbsolutePath());
    }
}
