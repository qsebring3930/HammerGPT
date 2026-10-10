using System.Text.Json;
using System.Reflection;
using ValveResourceFormat;
using ValveResourceFormat.ResourceTypes;

if (args.Length != 2 || File.Exists(args[1])) return 1;
using var resource = new Resource();
resource.Read(args[0]);
object Describe(object? value) => value == null ? new { type = "null", count = (int?)null }
    : new { type = value.GetType().FullName ?? value.GetType().Name, count = value is Array a ? (int?)a.Length : null };
var blocks = resource.Blocks.Select(block => new {
    type = block.GetType().FullName,
    properties = block.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance)
        .Where(p => p.CanRead && p.GetIndexParameters().Length == 0)
        .Select(p => { object? value = null; try { value = p.GetValue(block); } catch { }
            return new { name = p.Name, value = Describe(value) }; }).ToArray(),
    fields = block.GetType().GetFields(BindingFlags.Public | BindingFlags.Instance)
        .Select(f => new { name = f.Name, value = Describe(f.GetValue(block)) }).ToArray()
}).ToArray();
Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[1]))!);
var physics = resource.Blocks.OfType<PhysAggregateData>().FirstOrDefault();
var physicsParts = physics?.Parts.Select(part => new {
    collision_attribute_index = part.CollisionAttributeIndex,
    spheres = part.Shape.Spheres.Length, capsules = part.Shape.Capsules.Length,
    hulls = part.Shape.Hulls.Length, meshes = part.Shape.Meshes.Length
}).ToArray();
using var output = new FileStream(args[1], FileMode.CreateNew);
JsonSerializer.Serialize(output, new { source = Path.GetFullPath(args[0]), parser = "ValveResourceFormat 20.0.6980", blocks, physics_parts = physicsParts }, new JsonSerializerOptions { WriteIndented = true });
Console.WriteLine(JsonSerializer.Serialize(new { blocks = blocks.Select(b => b.type), physics_parts = physicsParts }));
return 0;
