use crate::types::Sample;
use crate::types::config::*;
pub struct OfdmSymbol;

impl OfdmSymbol {
    pub fn add_cyclic_prefix(
        data: Vec<Sample>,
        cyclic_prefix_type: CyclicPrefixType,
    ) -> Vec<Sample> {
        let cyclic_prefix_size = cyclic_prefix_type.size() as usize;

        let mut result: Vec<Sample> = Vec::with_capacity(data.len() + cyclic_prefix_size as usize);

        let cyclic_prefix = &data[data.len() - cyclic_prefix_size..data.len()];

        result.extend_from_slice(cyclic_prefix);
        result.extend(data);

        result
    }
}
